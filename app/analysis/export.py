"""Build the app-wide results export workbook (DOMAIN layer).

Pure transformation: takes the rows targets_with_latest_result() returns and
produces .xlsx bytes with openpyxl. Exports the *stored* detection answers --
it never recomputes, so the file always matches what the app has shown.
No Flask, no SQL, no audit (ADR 0001 layering).
"""

from __future__ import annotations

import io
import json

from openpyxl import Workbook

HEADERS = [
    "Target ID", "Target", "Phone number", "Dataset", "Analyzed at",
    "Home area", "Home confidence", "Work area", "Work confidence",
    "Frequent areas", "Frequent areas confidence",
]

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _detection(result: dict | None) -> tuple[str, str]:
    """(area, confidence label) with em-dash placeholders for empty windows."""
    if not result:
        return ("—", "—")
    return (
        result.get("area") or "—",
        result.get("confidence_label") or result.get("confidence") or "—",
    )


def build_results_workbook(rows: list[dict]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Detection results"
    ws.append(HEADERS)
    for row in rows:
        base = [row["id"], row["name"], row["phone_number"], row["dataset_name"]]
        if row["result_json"] is None:
            ws.append(base + ["not analyzed"] + [""] * 6)
            continue
        payload = json.loads(row["result_json"])
        home = _detection(payload.get("home"))
        work = _detection(payload.get("work"))
        frequent = ", ".join(
            f"{a['area']} ({a['count']})" for a in payload.get("frequent_areas") or []
        )
        ws.append(base + [
            payload.get("analyzed_at") or "",
            home[0], home[1], work[0], work[1],
            frequent, _detection(payload.get("frequent_areas_confidence"))[1],
        ])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
