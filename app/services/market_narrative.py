"""Market narrative generation (spec §16).

Strictly template-based over verified structured data already in the database — never
free-generated, and never a source of numbers that don't also exist in the underlying
tables. If a figure isn't in the database, the narrative omits the sentence rather than
guessing.
"""


def generate_narrative(report) -> str:
    stats = report.market_statistics
    sentences = []

    if stats and stats.equity_turnover is not None and stats.number_of_deals is not None:
        sentences.append(
            f"Equity trading recorded Frw {stats.equity_turnover:,.0f} in turnover across "
            f"{stats.number_of_deals:,} deals."
        )
    elif stats and stats.equity_turnover is not None:
        sentences.append(f"Equity trading recorded Frw {stats.equity_turnover:,.0f} in turnover.")

    indices = list(report.indices)
    for idx in indices:
        if idx.current_value is None:
            continue
        if idx.percentage_change is not None:
            direction = "gained" if idx.percentage_change >= 0 else "declined"
            sentences.append(
                f"The {idx.index_name} {direction} {abs(float(idx.percentage_change)):.2f}% to "
                f"{idx.current_value:,.2f}."
            )
        else:
            sentences.append(f"The {idx.index_name} closed at {idx.current_value:,.2f}.")

    equities_with_volume = [e for e in report.equities if e.volume is not None]
    if equities_with_volume:
        leader = max(equities_with_volume, key=lambda e: e.volume)
        sentences.append(f"Trading activity was concentrated in {leader.symbol}, "
                          f"which recorded volume of {leader.volume:,} shares.")

    if stats and stats.bond_turnover is not None:
        sentences.append(f"Bond market turnover totalled Frw {stats.bond_turnover:,.0f}.")

    if stats and stats.market_capitalization is not None:
        sentences.append(f"Total market capitalization stood at Frw {stats.market_capitalization:,.0f}.")

    if not sentences:
        return "No market summary is available yet — this report has not produced enough validated data."

    return " ".join(sentences)
