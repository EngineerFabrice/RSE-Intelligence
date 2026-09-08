"""Stage 6 — cross-section reconciliation (spec §9).

The same figures often appear more than once in an RSE report (e.g. total shares traded
in the market-statistics summary vs. the sum of individual equity volumes in the equity
table). This never silently picks a winner — every mismatch beyond tolerance becomes a
`validation_issues` row carrying both source values so a reviewer resolves it explicitly.
"""

TOLERANCE = 0.01  # 1% relative tolerance before treating a mismatch as a real conflict


def _within_tolerance(a, b, tol=TOLERANCE) -> bool:
    if a is None or b is None:
        return True  # nothing to compare — not a conflict
    a, b = float(a), float(b)
    if a == 0 and b == 0:
        return True
    denom = max(abs(a), abs(b), 1)
    return abs(a - b) / denom <= tol


def _conflict(field, record_label, expected, alternative, source_a, source_b, description,
              severity="critical", target_table=None, target_id=None):
    return {
        "issue_type": "conflict",
        "severity": severity,
        "target_table": target_table,
        "target_id": target_id,
        "field": field,
        "record_label": record_label,
        "expected_value": str(expected),
        "extracted_value": str(expected),
        "alternative_value": str(alternative),
        "source_a_label": source_a,
        "source_b_label": source_b,
        "description": description,
    }


def reconcile_report(report):
    """Returns a list of issue dicts (not yet persisted) describing detected conflicts."""
    issues = []
    equities = list(report.equities)
    stats = report.market_statistics
    bond_trades = list(report.bond_trades)

    if stats and equities:
        equity_volume_sum = sum(e.volume for e in equities if e.volume is not None)
        if stats.shares_traded is not None and not _within_tolerance(equity_volume_sum, stats.shares_traded):
            issues.append(_conflict(
                "shares_traded", "Total Shares Traded",
                stats.shares_traded, equity_volume_sum,
                "Market Statistics", "Equity Table (sum of volumes)",
                f"Market Statistics reports {stats.shares_traded:,.0f} shares traded, but the sum of "
                f"individual equity volumes in the equity table is {equity_volume_sum:,.0f}.",
                target_table="market_statistics", target_id=stats.id,
            ))

        equity_turnover_sum = sum(float(e.value_turnover) for e in equities if e.value_turnover is not None)
        if stats.equity_turnover is not None and not _within_tolerance(equity_turnover_sum, stats.equity_turnover):
            issues.append(_conflict(
                "equity_turnover", "Equity Turnover",
                stats.equity_turnover, equity_turnover_sum,
                "Market Statistics", "Equity Table (sum of value/turnover)",
                f"Market Statistics reports equity turnover of {stats.equity_turnover:,.2f}, but the sum of "
                f"individual equity values in the equity table is {equity_turnover_sum:,.2f}.",
                target_table="market_statistics", target_id=stats.id,
            ))

    if stats and bond_trades:
        bond_turnover_sum = sum(float(bt.value) for bt in bond_trades if bt.value is not None)
        if stats.bond_turnover is not None and not _within_tolerance(bond_turnover_sum, stats.bond_turnover):
            issues.append(_conflict(
                "bond_turnover", "Bond Turnover",
                stats.bond_turnover, bond_turnover_sum,
                "Market Statistics", "Bond Trades (sum of values)",
                f"Market Statistics reports bond turnover of {stats.bond_turnover:,.2f}, but the sum of "
                f"individual bond trade values is {bond_turnover_sum:,.2f}.",
                target_table="market_statistics", target_id=stats.id,
            ))

    return issues
