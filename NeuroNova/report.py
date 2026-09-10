"""
report.py — printable PDF caregiver report for Neuronova.

Generates a one-page-plus PDF summarising a patient's cognitive trend,
risk level, medicine adherence and reminders, so a caregiver can hand
it to a doctor / PHC without needing the app open.
Built on ReportLab (pure Python, no system binaries) so it works the same
on Streamlit Cloud as it does locally.
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.widgets.markers import makeMarker

import db
import cognitive_ai

PRIMARY = colors.HexColor("#2C6B64")
PRIMARY_LIGHT = colors.HexColor("#A8D4CD")
TEXT_MUTED = colors.HexColor("#55716B")
RISK_COLORS = {
    "Low": colors.HexColor("#2E8B57"),
    "Medium": colors.HexColor("#C77B00"),
    "High": colors.HexColor("#C0392B"),
    "Unknown": TEXT_MUTED,
}

GAME_LABELS = {"memory_match": "Memory Match", "pattern_recall": "Pattern Recall", "traditions_match": "Know Your Roots"}


def _trend_chart(days, daily_avg, width=16 * cm, height=6 * cm):
    """A simple line chart of daily average score, drawn with ReportLab
    graphics (no matplotlib dependency)."""
    drawing = Drawing(width, height)
    plot = LinePlot()
    plot.x = 40
    plot.y = 20
    plot.width = width - 70
    plot.height = height - 45
    plot.data = [list(zip(range(len(daily_avg)), daily_avg))]
    plot.lines[0].strokeColor = PRIMARY
    plot.lines[0].strokeWidth = 2
    plot.lines[0].symbol = makeMarker("Circle")
    plot.lines[0].symbol.strokeColor = PRIMARY
    plot.lines[0].symbol.fillColor = PRIMARY
    plot.lines[0].symbol.size = 4

    y_vals = daily_avg or [0]
    plot.yValueAxis.valueMin = max(0, min(y_vals) - 10)
    plot.yValueAxis.valueMax = min(100, max(y_vals) + 10)
    plot.yValueAxis.labelTextFormat = "%d"

    n = len(days)
    step = max(1, n // 6)
    plot.xValueAxis.valueMin = 0
    plot.xValueAxis.valueMax = max(1, n - 1)
    plot.xValueAxis.valueSteps = list(range(0, n, step))
    plot.xValueAxis.labelTextFormat = lambda v: days[int(v)][5:] if 0 <= int(v) < n else ""
    plot.xValueAxis.labels.fontSize = 6
    plot.xValueAxis.labels.angle = 30
    plot.xValueAxis.labels.dy = -8

    drawing.add(plot)
    return drawing


def generate_caregiver_report(patient, days=21):
    """Build the PDF report for one patient and return it as bytes."""
    reminders_today = db.get_reminders(patient["id"])
    adherence_pct, meds_done, meds_total = cognitive_ai.medicine_adherence(reminders_today)
    trend = cognitive_ai.analyze_trend(db.get_scores(patient["id"], days=days))

    breakdown_rows = []
    for gtype, glabel in GAME_LABELS.items():
        g_scores = db.get_scores(patient["id"], gtype, days=days)
        if g_scores:
            avg = sum(r["score"] for r in g_scores) / len(g_scores)
            breakdown_rows.append((glabel, len(g_scores), round(avg, 1)))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=1.6 * cm, bottomMargin=1.6 * cm, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
        title=f"Neuronova Cognitive Report — {patient['name']}",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("NNTitle", parent=styles["Title"], textColor=PRIMARY, fontSize=20, spaceAfter=2)
    sub_style = ParagraphStyle("NNSub", parent=styles["Normal"], textColor=TEXT_MUTED, fontSize=10)
    h2_style = ParagraphStyle("NNH2", parent=styles["Heading2"], textColor=PRIMARY, spaceBefore=14, spaceAfter=6)
    body_style = ParagraphStyle("NNBody", parent=styles["Normal"], fontSize=10.5, leading=15)
    disclaimer_style = ParagraphStyle("NNDisc", parent=styles["Normal"], fontSize=8, textColor=TEXT_MUTED)

    story = []

    story.append(Paragraph("Neuronova — Cognitive Health Report", title_style))
    story.append(Paragraph(
        f"Generated {datetime.now().strftime('%d %b %Y, %I:%M %p')} &middot; "
        f"For caregiver / physician use",
        sub_style,
    ))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=PRIMARY_LIGHT, thickness=1))
    story.append(Spacer(1, 10))

    # ReportLab's built-in fonts have no Bengali/Devanagari/Meitei glyphs, so use
    # the English part of the language name only (e.g. "Assamese", not the native
    # script) to avoid rendering as tofu boxes in the PDF.
    language_name = db.LANGUAGES.get(patient["language"], patient["language"]).split(" (")[0]

    patient_table = Table(
        [
            ["Patient", patient["name"], "Age", str(patient["age"])],
            ["Location", db.patient_location(patient), "Language", language_name],
        ],
        colWidths=[2.3 * cm, 6.2 * cm, 2.3 * cm, 5.7 * cm],
    )
    patient_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_MUTED),
        ("TEXTCOLOR", (2, 0), (2, -1), TEXT_MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("FONTNAME", (3, 0), (3, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(patient_table)

    story.append(Paragraph("Summary", h2_style))
    risk_color = RISK_COLORS.get(trend["risk"], TEXT_MUTED)
    summary_data = [
        ["7-day avg engagement", f"{trend['recent_avg']:.0f}%" if trend["has_data"] else "—"],
        ["Trend", trend["trend"]],
        ["Risk level", trend["risk"]],
        ["Medicine adherence today", f"{meds_done}/{meds_total} ({adherence_pct:.0f}%)" if meds_total else "—"],
    ]
    summary_table = Table(summary_data, colWidths=[6 * cm, 10.5 * cm])
    summary_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("TEXTCOLOR", (0, 0), (0, -1), TEXT_MUTED),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("TEXTCOLOR", (1, 2), (1, 2), risk_color),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, PRIMARY_LIGHT),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 8))

    rec_table = Table(
        [[Paragraph(f"<b>AI recommendation:</b> {trend['recommendation']}", body_style)]],
        colWidths=[16.5 * cm],
    )
    rec_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#EAF5F3")),
        ("BOX", (0, 0), (-1, -1), 0.6, PRIMARY_LIGHT),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(rec_table)

    if trend["has_data"] and len(trend["daily_avg"]) >= 2:
        story.append(Paragraph(f"{days}-Day Engagement Trend", h2_style))
        story.append(_trend_chart(trend["days"], trend["daily_avg"]))

    if breakdown_rows:
        story.append(Paragraph("Game-by-Game Breakdown", h2_style))
        table_data = [["Game", "Sessions", "Average score"]] + [
            [g, str(n), f"{avg:.1f}"] for g, n, avg in breakdown_rows
        ]
        bt = Table(table_data, colWidths=[7 * cm, 4.5 * cm, 5 * cm])
        bt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F8F7")]),
            ("GRID", (0, 0), (-1, -1), 0.4, PRIMARY_LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(bt)

    if reminders_today:
        story.append(Paragraph("Today's Reminders", h2_style))
        rem_data = [["Time", "Task", "Type", "Status"]] + [
            [r["time_str"], r["task"], r["type"], "Done" if r["done"] else "Pending"]
            for r in reminders_today
        ]
        rt = Table(rem_data, colWidths=[2.6 * cm, 8.4 * cm, 2.8 * cm, 2.7 * cm])
        rt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F8F7")]),
            ("GRID", (0, 0), (-1, -1), 0.4, PRIMARY_LIGHT),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(rt)

    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", color=PRIMARY_LIGHT, thickness=0.6))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "This report is generated by Neuronova's trend-detection engine (a Random Forest classifier "
        "over logged game scores) for caregiver reference only. It is not a clinical diagnosis — "
        "please consult a physician or the nearest primary health centre for medical evaluation.",
        disclaimer_style,
    ))

    doc.build(story)
    return buf.getvalue()
