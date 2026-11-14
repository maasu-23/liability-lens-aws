"""Render a drafts.Document to PDF with fpdf2's built-in Helvetica (no font files to ship).

The core fonts cover Latin-1 only, so amounts are written "Rs" rather than the rupee sign and any
other character outside Latin-1 is replaced. Documents are English for now.
"""

from __future__ import annotations

from fpdf import FPDF

from liability_lens.drafts import Document

_SWAPS = {"₹": "Rs ", "‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-",
          "…": "..."}


def _latin1(text: str) -> str:
    for k, v in _SWAPS.items():
        text = text.replace(k, v)
    return text.encode("latin-1", "replace").decode("latin-1")


def render(doc: Document) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_margins(18, 18, 18)
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_title(doc.title)
    pdf.set_creator("Liability Lens")
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(0, 7, _latin1(doc.title), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    for kind, *rest in doc.blocks:
        if kind == "h":
            pdf.ln(1)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, _latin1(rest[0]), new_x="LMARGIN", new_y="NEXT")
        elif kind == "p":
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(0, 5.5, _latin1(rest[0]), new_x="LMARGIN", new_y="NEXT")
        elif kind == "note":
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(90, 90, 90)
            pdf.multi_cell(0, 4.8, _latin1(rest[0]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)
        elif kind == "lines":
            pdf.set_font("Helvetica", "", 10.5)
            for line in rest[0]:
                pdf.multi_cell(0, 5.5, _latin1(line) or " ", new_x="LMARGIN", new_y="NEXT")
        elif kind == "list":
            pdf.set_font("Helvetica", "", 10.5)
            for i, item in enumerate(rest[0], 1):
                pdf.set_x(pdf.l_margin)
                pdf.cell(7, 5.5, f"{i}.")
                pdf.multi_cell(0, 5.5, _latin1(item), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(0.8)
        elif kind == "table":
            headers, rows = rest
            pdf.set_font("Helvetica", "", 9)
            widths = (9, 36, 22, 18, 46, 43)
            with pdf.table(col_widths=widths, text_align="LEFT", line_height=4.8) as table:
                head = table.row()
                for h in headers:
                    head.cell(_latin1(h))
                for r in rows:
                    row = table.row()
                    for c in r:
                        row.cell(_latin1(c))
        pdf.ln(2.5)
    return bytes(pdf.output())
