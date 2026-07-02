"""Build the app-wide results export workbook (DOMAIN layer).

Pure transformation: takes the rows targets_with_latest_result() returns and
produces .xlsx bytes with openpyxl. Exports the *stored* detection answers --
it never recomputes, so the file always matches what the app has shown.
No Flask, no SQL, no audit (ADR 0001 layering).

Layout: three sheets. "Summary" is one row per target with the gated answers
(home/work + their confidence); "Frequent areas" and "Frequent contacts" hold
the per-target tallies as real rows. Tallies deliberately carry NO confidence
column -- a count is not a gated verdict (same rule as the UI).
"""

from __future__ import annotations

import io
import json

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

HEADERS = [
    "Target ID", "Target", "Phone number", "Dataset", "Analyzed at",
    "Home area", "Home confidence", "Work area", "Work confidence",
    "Frequent areas",
]
AREAS_HEADERS = ["Target ID", "Target", "Phone number", "Rank", "Area", "Count", "Share"]
CONTACTS_HEADERS = ["Target ID", "Target", "Phone number", "Contact number",
                    "Total", "Calls out", "Calls in", "SMS out", "SMS in"]

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_HEADER_FONT = Font(bold=True, color="FFFFFF")
_HEADER_FILL = PatternFill("solid", fgColor="334155")
_NOT_ANALYZED_FONT = Font(italic=True, color="7F7F7F")


def _detection(result: dict | None) -> tuple[str, str]:
    """(area, confidence label) with em-dash placeholders for empty windows."""
    if not result:
        return ("—", "—")
    return (
        result.get("area") or "—",
        result.get("confidence_label") or result.get("confidence") or "—",
    )


def _fmt_when(iso: str | None) -> str:
    """ISO timestamp -> 'YYYY-MM-DD HH:MM' (readability over precision)."""
    return (iso or "").replace("T", " ")[:16]


def _finish_sheet(ws) -> None:
    """Styled sticky header, autofilter, content-sized columns."""
    for cell in ws[1]:
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for col_idx in range(1, ws.max_column + 1):
        letter = get_column_letter(col_idx)
        longest = max(
            (len(str(c.value)) for c in ws[letter] if c.value is not None),
            default=0,
        )
        ws.column_dimensions[letter].width = min(max(longest + 3, 11), 44)


def build_results_workbook(rows: list[dict]) -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    areas_ws = wb.create_sheet("Frequent areas")
    contacts_ws = wb.create_sheet("Frequent contacts")
    summary.append(HEADERS)
    areas_ws.append(AREAS_HEADERS)
    contacts_ws.append(CONTACTS_HEADERS)

    for row in rows:
        base = [row["id"], row["name"], row["phone_number"]]
        if row["result_json"] is None:
            summary.append(base + [row["dataset_name"], "not analyzed"] + [""] * 5)
            summary.cell(row=summary.max_row, column=5).font = _NOT_ANALYZED_FONT
            continue
        payload = json.loads(row["result_json"])
        home = _detection(payload.get("home"))
        work = _detection(payload.get("work"))
        frequent = payload.get("frequent_areas") or []
        summary.append(base + [
            row["dataset_name"], _fmt_when(payload.get("analyzed_at")),
            home[0], home[1], work[0], work[1],
            ", ".join(f"{a['area']} ({a['count']})" for a in frequent),
        ])
        for rank, a in enumerate(frequent, start=1):
            areas_ws.append(base + [rank, a.get("area"), a.get("count"), a.get("share")])
            areas_ws.cell(row=areas_ws.max_row, column=7).number_format = "0.0%"
        for c in payload.get("frequent_contacts") or []:
            contacts_ws.append(base + [c.get("number"), c.get("total"),
                                       c.get("call_out"), c.get("call_in"),
                                       c.get("sms_out"), c.get("sms_in")])

    for ws in (summary, areas_ws, contacts_ws):
        _finish_sheet(ws)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
