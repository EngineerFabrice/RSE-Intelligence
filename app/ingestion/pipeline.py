"""Orchestrates the full extraction pipeline (spec §7-§10, §41).

upload -> text extraction -> table extraction -> OCR fallback (if needed) ->
section classification -> field parsing -> normalization -> persistence ->
cross-section reconciliation -> confidence scoring -> validation issues
"""

import json
import logging
from datetime import datetime, timezone

from app.extensions import db
from app.ingestion import classifier
from app.ingestion.confidence import average_score, score_field, worst_level
from app.ingestion.normalizers import parse_date as normalize_date
from app.ingestion.ocr_fallback import extract_text_via_ocr
from app.ingestion.parsers.bond_trades_parser import parse_bond_trades
from app.ingestion.parsers.bonds_parser import parse_bonds
from app.ingestion.parsers.closing_bell_parser import parse_closing_bell
from app.ingestion.parsers.equities_parser import parse_equities
from app.ingestion.parsers.exchange_rates_parser import parse_exchange_rates
from app.ingestion.parsers.indices_parser import parse_indices
from app.ingestion.parsers.market_stats_parser import parse_market_statistics
from app.ingestion.reconciliation import reconcile_report
from app.ingestion.table_extraction import extract_tables
from app.ingestion.text_extraction import extract_native_text, total_extracted_chars
from app.models.bond import Bond
from app.models.bond_trade import BondTrade
from app.models.closing_bell import ClosingBellEntry
from app.models.equity import Equity
from app.models.exchange_rate import ExchangeRate
from app.models.extraction_diagnostic import ExtractionDiagnostic
from app.models.extraction_record import ExtractionRecord
from app.models.index import MarketIndex
from app.models.market_statistics import MarketStatistics
from app.models.report import Report
from app.models.validation_issue import ValidationIssue

logger = logging.getLogger("rse_intelligence.pipeline")

MIN_NATIVE_CHARS = 200  # below this, treat the document as scanned and try OCR


def _set_step(report: Report, status: str, step: str):
    report.processing_status = status
    report.processing_step = step
    db.session.commit()


def _record_diagnostic(report, section, pages, tables, raw_row_count, records, rejected,
                        extraction_method, notes=None):
    """Persist extraction observability for one section (spec §7) — makes a section
    that ends up empty (or partially rejected) inspectable instead of a bare
    'No data extracted for this section.'"""
    page_numbers = sorted({p.page_number for p in pages}) if pages else []
    pages_label = ",".join(str(n) for n in page_numbers) if page_numbers else None

    db.session.add(ExtractionDiagnostic(
        report_id=report.id,
        section=section,
        pages=pages_label,
        extraction_method=extraction_method,
        tables_detected=len(tables) if tables is not None else 0,
        tables_used=len(tables) if tables else 0,
        raw_rows=raw_row_count,
        accepted_rows=len(records),
        rejected_rows=len(rejected),
        records_persisted=len(records),
        rejection_reasons=json.dumps(rejected[:50]) if rejected else None,
        notes=notes,
    ))


def _lineage(report, table_name, target_id, field_name, value, record, field_confidence):
    db.session.add(ExtractionRecord(
        report_id=report.id,
        target_table=table_name,
        target_id=target_id,
        field_name=field_name,
        value=None if value is None else str(value),
        source_page=record.source_page,
        source_section=table_name,
        source_text=record.raw_text,
        extraction_method=record.extraction_method,
        confidence=field_confidence,
        validation_status="passed" if record.field_valid.get(field_name, True) else "failed",
    ))


def _score_record(record, has_conflict=False):
    # Records reconstructed via a fallback method (prose regex, positionally
    # reconstructed degenerate table rows) are flagged unusual-format so they route to
    # review rather than being silently treated as HIGH confidence just because every
    # individual field parsed without error.
    is_unusual_format = record.extraction_method in ("native_text_prose",)

    levels = []
    scores = []
    for field_name, is_valid in record.field_valid.items():
        level, score = score_field(
            is_valid=is_valid,
            was_ocr=record.was_ocr,
            has_conflict=has_conflict,
            is_missing_required=False,
            is_unusual_format=is_unusual_format,
        )
        levels.append(level)
        scores.append(score)
    return worst_level(levels), average_score(scores)


def _persist_equities(report, records):
    for rec in records:
        level, score = _score_record(rec)
        eq = Equity(
            report_id=report.id,
            isin=rec.fields.get("isin"),
            symbol=rec.fields.get("symbol"),
            security_name=rec.fields.get("security_name"),
            high_12m=rec.fields.get("high_12m"),
            low_12m=rec.fields.get("low_12m"),
            today_high=rec.fields.get("today_high"),
            today_low=rec.fields.get("today_low"),
            closing_price=rec.fields.get("closing_price"),
            previous_close=rec.fields.get("previous_close"),
            change=rec.fields.get("change"),
            change_percent=rec.fields.get("change_percent"),
            volume=rec.fields.get("volume"),
            value_turnover=rec.fields.get("value_turnover"),
            confidence_score=score,
            confidence_level=level,
            source_page=rec.source_page,
            source_section="equities",
            extraction_method=rec.extraction_method,
        )
        db.session.add(eq)
        db.session.flush()
        for field_name, value in rec.fields.items():
            _lineage(report, "equities", eq.id, field_name, value, rec, score)
        if level != "high":
            db.session.add(ValidationIssue(
                report_id=report.id, issue_type="format_error" if not all(rec.field_valid.values()) else "review",
                severity="warning" if level == "review_required" else "critical",
                target_table="equities", target_id=eq.id, field=None,
                record_label=eq.symbol, extracted_value=str(rec.fields),
                source_a_label="Equity Table", source_a_page=rec.source_page,
                description=f"{eq.symbol}: extraction confidence is {level.replace('_', ' ')}.",
            ))


def _persist_bonds(report, records):
    for rec in records:
        level, score = _score_record(rec)
        bond = Bond(
            report_id=report.id,
            isin=rec.fields.get("isin"),
            status=rec.fields.get("status"),
            security=rec.fields.get("security"),
            bond_type=rec.fields.get("bond_type", "government"),
            maturity_date=rec.fields.get("maturity_date"),
            tenor=rec.fields.get("tenor"),
            coupon=rec.fields.get("coupon"),
            close_price=rec.fields.get("close_price"),
            previous_value=rec.fields.get("previous_value"),
            bids=rec.fields.get("bids"),
            offers=rec.fields.get("offers"),
            traded_volume=rec.fields.get("traded_volume"),
            bond_traded=rec.fields.get("bond_traded", False),
            confidence_score=score,
            confidence_level=level,
            source_page=rec.source_page,
            source_section="bonds",
            extraction_method=rec.extraction_method,
        )
        db.session.add(bond)
        db.session.flush()
        for field_name, value in rec.fields.items():
            _lineage(report, "bonds", bond.id, field_name, value, rec, score)
        if level != "high":
            db.session.add(ValidationIssue(
                report_id=report.id, issue_type="format_error",
                severity="warning" if level == "review_required" else "critical",
                target_table="bonds", target_id=bond.id,
                record_label=bond.security, extracted_value=str(rec.fields),
                source_a_label="Bonds Table", source_a_page=rec.source_page,
                description=f"{bond.security}: extraction confidence is {level.replace('_', ' ')}.",
            ))


def _persist_bond_trades(report, records):
    for rec in records:
        level, score = _score_record(rec)
        trade = BondTrade(
            report_id=report.id,
            trade_date=rec.fields.get("trade_date") or report.report_date,
            isin=rec.fields.get("isin"),
            security=rec.fields.get("security"),
            price_yield=rec.fields.get("price_yield"),
            volume=rec.fields.get("volume"),
            value=rec.fields.get("value"),
            number_of_trades=rec.fields.get("number_of_trades"),
            confidence_score=score,
            confidence_level=level,
            source_page=rec.source_page,
            source_section="bond_trades",
            extraction_method=rec.extraction_method,
        )
        db.session.add(trade)
        db.session.flush()
        for field_name, value in rec.fields.items():
            _lineage(report, "bond_trades", trade.id, field_name, value, rec, score)


def _persist_indices(report, records):
    for rec in records:
        level, score = _score_record(rec)
        idx = MarketIndex(
            report_id=report.id,
            index_name=rec.fields.get("index_name"),
            current_value=rec.fields.get("current_value"),
            previous_value=rec.fields.get("previous_value"),
            change=rec.fields.get("change"),
            percentage_change=rec.fields.get("percentage_change"),
            confidence_score=score,
            confidence_level=level,
            source_page=rec.source_page,
            source_section="indices",
            extraction_method=rec.extraction_method,
        )
        db.session.add(idx)
        db.session.flush()
        for field_name, value in rec.fields.items():
            _lineage(report, "indices", idx.id, field_name, value, rec, score)


def _persist_exchange_rates(report, records):
    for rec in records:
        level, score = _score_record(rec)
        fx = ExchangeRate(
            report_id=report.id,
            currency=rec.fields.get("currency"),
            buy_rate=rec.fields.get("buy_rate"),
            sell_rate=rec.fields.get("sell_rate"),
            average_rate=rec.fields.get("average_rate"),
            confidence_score=score,
            confidence_level=level,
            source_page=rec.source_page,
            source_section="exchange_rates",
            extraction_method=rec.extraction_method,
        )
        db.session.add(fx)
        db.session.flush()
        for field_name, value in rec.fields.items():
            _lineage(report, "exchange_rates", fx.id, field_name, value, rec, score)
        if level != "high":
            db.session.add(ValidationIssue(
                report_id=report.id, issue_type="format_error", severity="warning",
                target_table="exchange_rates", target_id=fx.id,
                record_label=fx.currency, extracted_value=str(rec.fields),
                source_a_label="Exchange Rates Table", source_a_page=rec.source_page,
                description=f"Currency '{fx.currency}' could not be fully validated.",
            ))


def _persist_closing_bell(report, records):
    for rec in records:
        level, score = _score_record(rec)
        entry = ClosingBellEntry(
            report_id=report.id,
            security=rec.fields.get("security"),
            bid_quantity=rec.fields.get("bid_quantity"),
            bid_price=rec.fields.get("bid_price"),
            offer_quantity=rec.fields.get("offer_quantity"),
            offer_price=rec.fields.get("offer_price"),
            has_bid=rec.fields.get("has_bid", False),
            has_offer=rec.fields.get("has_offer", False),
            status=rec.fields.get("status"),
            confidence_score=score,
            confidence_level=level,
            source_page=rec.source_page,
            source_section="closing_bell",
            extraction_method=rec.extraction_method,
        )
        db.session.add(entry)
        db.session.flush()
        for field_name, value in rec.fields.items():
            _lineage(report, "closing_bell", entry.id, field_name, value, rec, score)
        if level != "high":
            db.session.add(ValidationIssue(
                report_id=report.id, issue_type="narrative_source" if rec.extraction_method == "native_text_prose"
                else "format_error",
                severity="warning",
                target_table="closing_bell", target_id=entry.id,
                record_label=entry.security, extracted_value=str(rec.fields),
                source_a_label="Closing Bell", source_a_page=rec.source_page,
                description=f"{entry.security}: closing bell entry was extracted from narrative text and "
                            f"should be double-checked against the source PDF."
                if rec.extraction_method == "native_text_prose"
                else f"{entry.security}: extraction confidence is {level.replace('_', ' ')}.",
            ))


def _persist_market_statistics(report, record):
    if record is None:
        return
    level, score = _score_record(record)
    stats = MarketStatistics(
        report_id=report.id,
        shares_traded=record.fields.get("shares_traded"),
        equity_turnover=record.fields.get("equity_turnover"),
        bond_turnover=record.fields.get("bond_turnover"),
        number_of_deals=record.fields.get("number_of_deals"),
        market_capitalization=record.fields.get("market_capitalization"),
        repo_value=record.fields.get("repo_value"),
        repo_deals=record.fields.get("repo_deals"),
        repo_tenor=record.fields.get("repo_tenor"),
        repo_rate=record.fields.get("repo_rate"),
        confidence_score=score,
        confidence_level=level,
        source_page=record.source_page,
        source_section="market_statistics",
        extraction_method=record.extraction_method,
    )
    db.session.add(stats)
    db.session.flush()
    for field_name, value in record.fields.items():
        _lineage(report, "market_statistics", stats.id, field_name, value, record, score)
    if level != "high":
        db.session.add(ValidationIssue(
            report_id=report.id, issue_type="missing_field", severity="warning",
            target_table="market_statistics", target_id=stats.id,
            record_label="Market Statistics", extracted_value=str(record.fields),
            source_a_label="Market Statistics", source_a_page=record.source_page,
            description="One or more core market statistics fields could not be reliably extracted.",
        ))


def process_report(report_id: int):
    report = db.session.get(Report, report_id)
    if report is None:
        logger.error("process_report called with unknown report_id=%s", report_id)
        return

    try:
        _set_step(report, "processing", "Document verified")

        pages, metadata = extract_native_text(report.storage_path)
        extraction_method = "native_text"

        if total_extracted_chars(pages) < MIN_NATIVE_CHARS:
            _set_step(report, "processing", "Native text insufficient — attempting OCR")
            ocr_pages, ocr_status = extract_text_via_ocr(report.storage_path)
            if ocr_status == "success" and ocr_pages:
                pages = ocr_pages
                extraction_method = "ocr"
            elif ocr_status == "unavailable":
                db.session.add(ValidationIssue(
                    report_id=report.id, issue_type="ocr_used", severity="critical",
                    description="This document appears to be scanned and OCR is not available on this "
                                "server. Text extraction may be incomplete.",
                ))

        _set_step(report, "processing", "Text extracted")

        tables = extract_tables(report.storage_path)
        _set_step(report, "processing", "Tables detected")

        classification = classifier.classify_document(pages)
        report.layout_confidence = classification.layout_confidence
        report.is_new_format = classification.is_new_format
        if classification.detected_report_date_text:
            detected = normalize_date(classification.detected_report_date_text)
            if detected:
                report.report_date = detected
        if report.is_new_format:
            db.session.add(ValidationIssue(
                report_id=report.id, issue_type="new_layout", severity="warning",
                description=f"This report's structure differs from the expected RSE layout "
                            f"(layout confidence {classification.layout_confidence:.0%}). Review recommended.",
            ))
        _set_step(report, "processing", "Sections classified")

        eq_pages = classifier.pages_for_section(classification, "equities", pages)
        eq_tables = classifier.tables_for_pages(tables, [p.page_number for p in eq_pages]) or tables
        eq_records, eq_rejected = parse_equities(eq_tables, extraction_method)
        _persist_equities(report, eq_records)
        _record_diagnostic(report, "equities", eq_pages, eq_tables, len(eq_records) + len(eq_rejected),
                            eq_records, eq_rejected, extraction_method)
        _set_step(report, "processing", "Equities identified")

        bond_pages = classifier.pages_for_section(classification, "bonds", pages)
        bond_tables = classifier.tables_for_pages(tables, [p.page_number for p in bond_pages])
        bond_records, bond_rejected = parse_bonds(bond_tables, extraction_method)
        _persist_bonds(report, bond_records)
        _record_diagnostic(report, "bonds", bond_pages, bond_tables, len(bond_records) + len(bond_rejected),
                            bond_records, bond_rejected, extraction_method)

        trade_pages = classifier.pages_for_section(classification, "bond_trades", pages)
        trade_tables = classifier.tables_for_pages(tables, [p.page_number for p in trade_pages])
        trade_records, trade_rejected = parse_bond_trades(trade_tables, extraction_method)
        _persist_bond_trades(report, trade_records)
        _record_diagnostic(report, "bond_trades", trade_pages, trade_tables,
                            len(trade_records) + len(trade_rejected), trade_records, trade_rejected,
                            extraction_method,
                            notes=None if trade_pages else "No distinct bond-trades section was detected "
                                                            "in this report (some RSE reports don't include one).")
        _set_step(report, "processing", "Bonds identified")

        stats_pages = classifier.pages_for_section(classification, "market_statistics", pages) or pages
        stats_record = parse_market_statistics(stats_pages, extraction_method)
        _persist_market_statistics(report, stats_record)
        _record_diagnostic(report, "market_statistics", stats_pages, None, 1 if stats_record else 0,
                            [stats_record] if stats_record else [], [], extraction_method)
        _set_step(report, "processing", "Market statistics identified")

        fx_pages = classifier.pages_for_section(classification, "exchange_rates", pages)
        fx_tables = classifier.tables_for_pages(tables, [p.page_number for p in fx_pages])
        fx_records, fx_rejected = parse_exchange_rates(fx_tables, extraction_method)
        _persist_exchange_rates(report, fx_records)
        _record_diagnostic(report, "exchange_rates", fx_pages, fx_tables, len(fx_records) + len(fx_rejected),
                            fx_records, fx_rejected, extraction_method)
        _set_step(report, "processing", "Exchange rates identified")

        idx_pages = classifier.pages_for_section(classification, "indices", pages) or pages
        idx_tables = classifier.tables_for_pages(tables, [p.page_number for p in idx_pages])
        idx_records, idx_rejected = parse_indices(idx_tables, idx_pages, extraction_method)
        _persist_indices(report, idx_records)
        _record_diagnostic(report, "indices", idx_pages, idx_tables, len(idx_records) + len(idx_rejected),
                            idx_records, idx_rejected, extraction_method)

        cb_pages = classifier.pages_for_section(classification, "closing_bell", pages)
        cb_tables = classifier.tables_for_pages(tables, [p.page_number for p in cb_pages])
        cb_records, cb_rejected = parse_closing_bell(cb_tables, cb_pages or pages, extraction_method)
        _persist_closing_bell(report, cb_records)
        cb_method = cb_records[0].extraction_method if cb_records else extraction_method
        _record_diagnostic(report, "closing_bell", cb_pages, cb_tables, len(cb_records) + len(cb_rejected),
                            cb_records, cb_rejected, cb_method)

        db.session.commit()
        _set_step(report, "processing", "Cross-validation running")

        for issue in reconcile_report(report):
            db.session.add(ValidationIssue(report_id=report.id, **issue))
        db.session.commit()

        overall = average_score([r.confidence for r in report.extraction_records])
        report.overall_confidence = overall

        open_critical = report.validation_issues.filter_by(severity="critical", resolution=None).count()
        open_any = report.validation_issues.filter_by(resolution=None).count()

        report.validation_status = "issues_found" if open_any else "passed"
        report.processing_status = "review_required" if (open_any or open_critical) else "validation_required"
        report.processing_step = "Finalizing report"
        report.upload_time = report.upload_time or datetime.now(timezone.utc)
        db.session.commit()

    except Exception as exc:  # noqa: BLE001 - pipeline must fail safely, never crash the worker
        logger.exception("Report processing failed for report_id=%s", report_id)
        db.session.rollback()
        report = db.session.get(Report, report_id)
        if report:
            report.processing_status = "failed"
            report.processing_error = str(exc)
            report.processing_step = "Processing failed"
            db.session.commit()
