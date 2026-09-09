"""Tests for "Ask RSE Market" (spec: Phase 4).

Covers the RBAC matrix (Administrator/Analyst only), the query-tool layer
(app/services/rse_query_tools.py) directly -- real data, no fabricated
values, correct historical dates, correct calculations, source/verification
metadata -- and the API endpoint's handling of the AI layer, always with the
OpenAI client replaced by a scripted fake so tests never make a real network
call regardless of what OPENAI_API_KEY happens to be set to in the
environment.
"""

import json
from datetime import date
from types import SimpleNamespace

from tests.fixtures.sample_report import build_sample_pdf

from app.extensions import db
from app.ingestion.pipeline import process_report
from app.models.audit_log import AuditLog
from app.models.report import Report
from app.services import duplicate_detection, rse_query_tools as tools
from app.services.ai_assistant import answer_question


def _seed_approved_report(app, tmp_path, name="sample.pdf", report_date=None):
    pdf_path = tmp_path / name
    build_sample_pdf(pdf_path, shares_traded_mismatch=False)
    file_bytes = pdf_path.read_bytes()

    report = Report(filename=name, original_filename=name,
                     file_hash=duplicate_detection.compute_file_hash(file_bytes), storage_path=str(pdf_path))
    db.session.add(report)
    db.session.commit()
    process_report(report.id)
    db.session.refresh(report)

    report.approval_status = "approved"
    report.processing_status = "approved"
    if report_date is not None:
        report.report_date = report_date
    db.session.commit()
    db.session.refresh(report)
    return report


# ---------------------------------------------------------------------------
# Fake OpenAI client -- scripted responses, no network access whatsoever.

class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = _FakeFunction(name, json.dumps(arguments))


def _fake_response(content=None, tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _FakeCompletions:
    def __init__(self, script):
        self._script = list(script)
        self.received_messages = []

    def create(self, **kwargs):
        self.received_messages.append(kwargs.get("messages"))
        if not self._script:
            raise AssertionError("Fake OpenAI script ran out of scripted responses.")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class _FakeClient:
    def __init__(self, script):
        self.chat = SimpleNamespace(completions=_FakeCompletions(script))


def _fake_openai_factory(script):
    """A drop-in replacement for openai.OpenAI(api_key=...) that replays `script`."""
    def _factory(api_key=None, **kwargs):
        return _FakeClient(script)
    return _factory


def _install_fake_openai(app, monkeypatch, script, api_key="test-key"):
    app.config["OPENAI_API_KEY"] = api_key
    monkeypatch.setattr("app.services.ai_assistant.OpenAI", _fake_openai_factory(script))


# ---------------------------------------------------------------------------
# 1-5: RBAC matrix

def test_admin_can_access_assistant_page(admin_client):
    resp = admin_client.get("/assistant/")
    assert resp.status_code == 200
    assert "Ask RSE Market" in resp.get_data(as_text=True)


def test_analyst_can_access_assistant_page(analyst_client):
    resp = analyst_client.get("/assistant/")
    assert resp.status_code == 200
    assert "Ask RSE Market" in resp.get_data(as_text=True)


def test_viewer_cannot_access_assistant_page(viewer_client):
    assert viewer_client.get("/assistant/").status_code == 403
    resp = viewer_client.post("/api/assistant/ask", json={"question": "test"})
    assert resp.status_code == 403


def test_reviewer_cannot_access_assistant_page(reviewer_client):
    assert reviewer_client.get("/assistant/").status_code == 403
    resp = reviewer_client.post("/api/assistant/ask", json={"question": "test"})
    assert resp.status_code == 403


def test_unauthenticated_cannot_access_assistant_page(client):
    resp = client.get("/assistant/")
    assert resp.status_code in (302, 401, 403)
    if resp.status_code == 302:
        assert "/auth/login" in resp.headers["Location"]

    api_resp = client.post("/api/assistant/ask", json={"question": "test"})
    assert api_resp.status_code == 401


def test_nav_link_shown_for_admin(admin_client):
    assert "Ask RSE Market" in admin_client.get("/").get_data(as_text=True)


def test_nav_link_hidden_for_viewer(viewer_client):
    assert "Ask RSE Market" not in viewer_client.get("/").get_data(as_text=True)


def test_nav_link_hidden_for_reviewer(reviewer_client):
    assert "Ask RSE Market" not in reviewer_client.get("/").get_data(as_text=True)


# ---------------------------------------------------------------------------
# 6-10: the query-tool layer itself -- real data, no hallucination, correct
# dates, correct calculations, source/verification metadata. No OpenAI
# involved at all; these test the deterministic backend directly.

def test_get_equity_returns_real_verified_data(app, tmp_path):
    _seed_approved_report(app, tmp_path)
    result = tools.get_equity("BLR")

    assert result["found"] is True
    assert result["equity"]["closing_price"] == 515.0
    assert result["equity"]["previous_close"] == 500.0
    assert result["equity"]["volume"] == 100
    assert result["report"]["verified"] is True
    assert result["report"]["report_date"] == "2026-09-07"


def test_missing_equity_is_not_hallucinated(app, tmp_path):
    _seed_approved_report(app, tmp_path)

    result = tools.get_equity("NOSUCHTICKER")
    assert result["found"] is False
    assert "equity" not in result
    assert "NOSUCHTICKER" in result["message"]


def test_missing_field_stays_none_not_zero(app, tmp_path):
    # The fixture PDF's equity table has no "today's high/low" columns, so the
    # parser correctly leaves these fields unset -- the tool must surface that
    # as None, never coerce it to 0.
    _seed_approved_report(app, tmp_path)
    result = tools.get_equity("BOK")
    assert result["equity"]["today_high"] is None
    assert result["equity"]["today_low"] is None


def test_equity_history_uses_correct_report_dates(app, tmp_path):
    older = _seed_approved_report(app, tmp_path, name="a.pdf", report_date=date(2026, 9, 1))
    newer = _seed_approved_report(app, tmp_path, name="b.pdf", report_date=date(2026, 9, 8))
    assert older.id != newer.id

    result = tools.get_equity_history("BOK", limit=10)
    assert result["found"] is True
    dates = [h["report_date"] for h in result["history"]]
    assert dates == sorted(dates)  # oldest to newest
    assert dates[0] == "2026-09-01"
    assert dates[-1] == "2026-09-08"


def test_top_performers_and_comparison_calculations_are_correct(app, tmp_path):
    _seed_approved_report(app, tmp_path)

    ranking = tools.top_performers(metric="volume", limit=5)
    assert ranking["found"] is True
    assert ranking["ranking"][0]["symbol"] == "BOK"  # 21,600 shares > BLR's 100
    assert ranking["ranking"][0]["volume"] == 21600

    comparison = tools.compare_equities(["BOK", "BLR"])
    assert comparison["found"] is True
    diff = comparison["comparison"]
    assert diff["closing_price_difference"] == 145.0  # 660 - 515
    assert diff["volume_difference"] == 21500  # 21600 - 100


def test_source_and_verification_metadata_present(app, tmp_path):
    _seed_approved_report(app, tmp_path)
    result = tools.get_market_overview()

    assert result["found"] is True
    assert result["report"]["report_id"] is not None
    assert result["report"]["report_date"] == "2026-09-07"
    assert result["report"]["verified"] is True
    assert result["report"]["status"] == "Verified"


def test_latest_report_status_distinguishes_unverified_from_verified(app, tmp_path):
    verified = _seed_approved_report(app, tmp_path, name="verified.pdf", report_date=date(2026, 9, 1))

    # A second, later report that has NOT been approved.
    pdf_path = tmp_path / "pending.pdf"
    build_sample_pdf(pdf_path, shares_traded_mismatch=False)
    unverified = Report(filename="pending.pdf", original_filename="pending.pdf",
                         file_hash=duplicate_detection.compute_file_hash(pdf_path.read_bytes()),
                         storage_path=str(pdf_path))
    db.session.add(unverified)
    db.session.commit()
    process_report(unverified.id)
    db.session.refresh(unverified)
    unverified.report_date = date(2026, 9, 8)
    db.session.commit()

    status = tools.get_latest_report_status()
    assert status["found"] is True
    assert status["most_recent_report"]["report_id"] == unverified.id
    assert status["most_recent_report"]["verified"] is False
    assert status["latest_verified_report"]["report_id"] == verified.id
    assert status["latest_is_verified"] is False


def test_no_verified_data_available_is_stated_clearly(app):
    # No report has been uploaded/approved at all.
    result = tools.get_equity("BOK")
    assert result["found"] is False
    assert "message" in result

    overview = tools.get_market_overview()
    assert overview["found"] is False
    assert "message" in overview


# ---------------------------------------------------------------------------
# 11: OpenAI/API failures are handled safely; the assistant is never
# "unconfigured" silently, and never leaks internal error detail.

def test_assistant_not_configured_returns_clear_message(app):
    app.config["OPENAI_API_KEY"] = None
    result = answer_question("What was the latest market activity?")
    assert result["configured"] is False
    assert "configured" in result["answer"].lower()
    assert result["sources"] == []


def test_assistant_handles_openai_failure_gracefully(app, monkeypatch):
    _install_fake_openai(app, monkeypatch, script=[RuntimeError("simulated network failure")])

    result = answer_question("What was the latest market activity?")
    assert result["configured"] is True
    assert result.get("error") is True
    assert "temporarily unavailable" in result["answer"].lower()
    # No internal exception text/traceback leaks into the user-facing answer.
    assert "RuntimeError" not in result["answer"]
    assert "simulated network failure" not in result["answer"]


def test_ask_endpoint_handles_openai_failure_without_500(admin_client, app, monkeypatch):
    _install_fake_openai(app, monkeypatch, script=[RuntimeError("boom")])

    resp = admin_client.post("/api/assistant/ask", json={"question": "What was the latest market activity?"})
    assert resp.status_code == 200
    body = resp.get_json()["data"]
    assert body["error"] is True
    assert "boom" not in body["answer"]


def test_ask_endpoint_rejects_empty_and_oversized_questions(admin_client):
    assert admin_client.post("/api/assistant/ask", json={"question": ""}).status_code == 400
    assert admin_client.post("/api/assistant/ask", json={"question": "x" * 501}).status_code == 400


# ---------------------------------------------------------------------------
# Full round-trip through the API with a scripted tool call -- confirms the
# endpoint actually executes the real backend tool against real seeded data
# (not anything the fake model invents) and returns it with source metadata.

def test_ask_endpoint_executes_real_tool_and_returns_sources(admin_client, app, tmp_path, monkeypatch):
    report = _seed_approved_report(app, tmp_path)

    tool_call = _FakeToolCall("call_1", "get_equity", {"symbol": "BLR"})
    script = [
        _fake_response(content=None, tool_calls=[tool_call]),
        _fake_response(content="BLR closed at 515.00, up from a previous close of 500.00, "
                                "as of the 2026-09-07 verified report."),
    ]
    _install_fake_openai(app, monkeypatch, script)

    resp = admin_client.post("/api/assistant/ask", json={"question": "What was BLR's closing price?"})
    assert resp.status_code == 200
    body = resp.get_json()["data"]

    assert body["configured"] is True
    assert "515" in body["answer"]
    assert body["used_tools"] == ["get_equity"]
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["report_id"] == report.id
    assert source["report_date"] == "2026-09-07"
    assert source["verified"] is True
    assert source["section"] == "Equities"

    # The AI query was audit-logged, consistent with the rest of the platform.
    entry = AuditLog.query.filter_by(action="ai_query").order_by(AuditLog.id.desc()).first()
    assert entry is not None
    assert "BLR" in entry.description


def test_analyst_can_successfully_ask_a_question(analyst_client, app, tmp_path, monkeypatch):
    _seed_approved_report(app, tmp_path)
    script = [_fake_response(content="No tool needed for this greeting.", tool_calls=None)]
    _install_fake_openai(app, monkeypatch, script)

    resp = analyst_client.post("/api/assistant/ask", json={"question": "hello"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["configured"] is True
