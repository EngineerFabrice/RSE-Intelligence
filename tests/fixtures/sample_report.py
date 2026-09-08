"""Builds a synthetic RSE-style market report PDF for tests only.

This is NOT real market data and is never referenced by application logic — it exists
purely so the extraction pipeline can be exercised end-to-end without a real official
RSE PDF (none was available when this platform was built; see the build plan).
"""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STYLES = getSampleStyleSheet()


def _table(data):
    t = Table(data, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.75, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    return t


def build_sample_pdf(path, shares_traded_mismatch=True):
    doc = SimpleDocTemplate(str(path), pagesize=A4, topMargin=1.5 * cm, bottomMargin=1.5 * cm)
    story = []

    story.append(Paragraph("Rwanda Stock Exchange — Daily Market Report", STYLES["Title"]))
    story.append(Paragraph("Report Date: 07 September 2026", STYLES["Normal"]))
    story.append(Spacer(1, 12))

    story.append(Paragraph("MARKET STATISTICS", STYLES["Heading2"]))
    shares_traded = "50,000" if shares_traded_mismatch else "21,700"
    story.append(Paragraph(f"Shares Traded: {shares_traded}", STYLES["Normal"]))
    story.append(Paragraph("Equity Turnover: 14,307,500", STYLES["Normal"]))
    story.append(Paragraph("Bond Turnover: 101,250", STYLES["Normal"]))
    story.append(Paragraph("Number of Deals: 15", STYLES["Normal"]))
    story.append(Paragraph("Market Capitalization: 500,000,000", STYLES["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("RSI: 132.45 (1.20%)", STYLES["Normal"]))
    story.append(Paragraph("ALSI: 145.67 (-0.50%)", STYLES["Normal"]))
    story.append(PageBreak())

    story.append(Paragraph("EQUITY SECURITIES", STYLES["Heading2"]))
    story.append(_table([
        ["ISIN", "Security", "12M High", "12M Low", "Closing Price", "Previous Closing", "Change", "Volume", "Value"],
        ["RW0001100008", "BOK", "700", "600", "660", "660", "0.00", "21600", "14256000"],
        ["RW0002100004", "BLR", "600", "480", "515", "500", "15.00", "100", "51500"],
    ]))
    story.append(PageBreak())

    story.append(Paragraph("GOVERNMENT BOND MARKET", STYLES["Heading2"]))
    story.append(_table([
        ["ISIN", "Security", "Maturity Date", "Tenor", "Coupon", "Closing Price"],
        ["RWFGB0012027", "Treasury Bond 2027", "15 June 2027", "5 Year", "12.50", "101.25"],
    ]))
    story.append(PageBreak())

    story.append(Paragraph("BOND TRADES", STYLES["Heading2"]))
    story.append(_table([
        ["Trade Date", "ISIN", "Security", "Price", "Volume", "Value"],
        ["07 September 2026", "RWFGB0012027", "Treasury Bond 2027", "101.25", "1000", "101250"],
    ]))
    story.append(PageBreak())

    story.append(Paragraph("EXCHANGE RATE", STYLES["Heading2"]))
    story.append(_table([
        ["Currency", "Buying Rate", "Selling Rate", "Average Rate"],
        ["USD", "1280.00", "1300.00", "1290.00"],
        ["KES", "9.50", "9.80", "9.65"],
    ]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("CLOSING BELL", STYLES["Heading2"]))
    story.append(_table([
        ["Security", "Bid Quantity", "Bid Price", "Offer Quantity", "Offer Price"],
        ["BOK", "500", "658", "300", "662"],
        ["BLR", "-", "-", "-", "-"],
    ]))

    doc.build(story)
    return path
