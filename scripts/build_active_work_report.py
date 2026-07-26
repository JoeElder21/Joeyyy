"""Render the dated active-work Markdown report as a public PDF artifact."""

from __future__ import annotations

from html import escape
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "reports" / "JOEYYY_ACTIVE_WORK_REPORT_2026-07-25.md"
OUTPUT = ROOT / "docs" / "reports" / "JOEYYY_ACTIVE_WORK_REPORT_2026-07-25.pdf"


def inline_markup(text: str) -> str:
    rendered = escape(text)
    rendered = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", rendered)
    return rendered


def build() -> None:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        KeepTogether,
        PageTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Title007",
            parent=styles["Title"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#14213d"),
            alignment=TA_CENTER,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1007",
            parent=styles["Heading1"],
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#14213d"),
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2007",
            parent=styles["Heading2"],
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#9b2226"),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Body007",
            parent=styles["BodyText"],
            fontSize=8.8,
            leading=12,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Bullet007",
            parent=styles["BodyText"],
            fontSize=8.8,
            leading=12,
            leftIndent=14,
            firstLineIndent=-7,
            bulletIndent=5,
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Footer007",
            parent=styles["BodyText"],
            fontSize=7,
            textColor=colors.grey,
        )
    )

    def page(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#d9d9d9"))
        canvas.line(0.65 * inch, 0.48 * inch, 7.85 * inch, 0.48 * inch)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(
            0.65 * inch,
            0.30 * inch,
            "JoeElder21/Joeyyy active-work report — 2026-07-25",
        )
        canvas.drawRightString(7.85 * inch, 0.30 * inch, f"Page {doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.58 * inch,
        title="Joeyyy active work and branch closeout report",
        author="Codex",
        invariant=1,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates(PageTemplate(id="report", frames=frame, onPage=page))

    story = []
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            story.append(Spacer(1, 3))
        elif line.startswith("# "):
            story.append(Paragraph(inline_markup(line[2:]), styles["Title007"]))
        elif line.startswith("## "):
            story.append(Paragraph(inline_markup(line[3:]), styles["H1007"]))
        elif line.startswith("### "):
            story.append(Paragraph(inline_markup(line[4:]), styles["H2007"]))
        elif line.startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            index -= 1
            rows = [
                [cell.strip() for cell in row.strip("|").split("|")]
                for row in table_lines
            ]
            rows = [row for pos, row in enumerate(rows) if pos != 1]
            cells = [
                [Paragraph(inline_markup(cell), styles["Body007"]) for cell in row]
                for row in rows
            ]
            table = Table(
                cells,
                repeatRows=1,
                colWidths=[doc.width * 0.48]
                + [doc.width * 0.13] * (len(cells[0]) - 2)
                + [doc.width * (0.52 - 0.13 * (len(cells[0]) - 2))],
            )
            table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#14213d")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#b7b7b7")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(KeepTogether([table, Spacer(1, 5)]))
        elif re.match(r"^\d+\. ", line) or line.startswith("- "):
            text = re.sub(r"^(?:\d+\.|-)\s+", "", line)
            story.append(
                Paragraph(inline_markup(text), styles["Bullet007"], bulletText="•")
            )
        else:
            story.append(Paragraph(inline_markup(line), styles["Body007"]))
        index += 1
    doc.build(story)


if __name__ == "__main__":
    build()
