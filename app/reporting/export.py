"""Build the app-wide results export workbook (DOMAIN layer).

Moved from app/analysis/export.py when the workbook started composing rows from
more than one domain (analysis detections + matching pair results); app/reporting
is the cross-domain report surface, deliberately OUTSIDE the domain-independence
set. Pure transformation: takes stored rows and produces .xlsx bytes with
openpyxl. Exports the *stored* answers -- it never recomputes, so the file always
matches what the app has shown. No Flask, no SQL, no audit (ADR 0001 layering).

Layout: six sheets, always all present so the workbook shape is predictable.
"Summary" is one row per target with the gated answers; "Frequent areas" and
"Frequent contacts" hold the per-target tallies as real rows (deliberately NO
confidence column -- a count is not a gated verdict, same rule as the UI).
"Contact matches" holds one row per finding of each SAVED pair match;
"Pair records" the capped, explicitly disclosed record ledger of each SAVED pair
(with dates/times and no confidence: these are records, not verdicts); "Frequency
counts" one row per ranked value of each SAVED explorer tally. The staged sheets
are click-to-save: nothing lands automatically.
"""

from __future__ import annotations

import io
import json

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
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
MATCHES_HEADERS = ["Match ID", "Dataset", "Target A", "Target B", "Saved at",
                   "Finding", "Strength", "Bound by", "Headline", "Key evidence",
                   "Dataset mode", "Near-boundary notes"]
TALLIES_HEADERS = ["Count ID", "Target", "Phone number", "Dataset", "Saved at",
                   "Filters", "Total records", "Rank", "Value", "Count"]
# The pair record ledger: actual records, with any cap disclosed in the final
# column. No confidence column because records are not verdicts.
LEDGER_HEADERS = ["Ledger ID", "Dataset", "Pair", "Saved at", "Category", "Who",
                  "Phone", "Date & time", "Call type", "Duration (s)",
                  "Other party", "Other party name", "Also a target", "Area",
                  "Distinctive", "Listing note"]

# Excel permits 1,048,576 rows per sheet. Reserve row 1 for the header and never
# let aggregate saved ledgers cross the remaining hard limit.
LEDGER_EXPORT_ROW_BUDGET = 1_048_575

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


class _StreamingSheet:
    """Small write-only worksheet facade that preserves the export styling."""

    def __init__(self, workbook, title: str, headers: list[str]):
        self.ws = workbook.create_sheet(title)
        self.headers = headers
        self.row_count = 0
        self.ws.freeze_panes = "A2"
        for col_idx, header in enumerate(headers, start=1):
            letter = get_column_letter(col_idx)
            self.ws.column_dimensions[letter].width = min(max(len(header) + 3, 11), 44)
        self.append(headers, header=True)

    def append(self, values, *, header=False, italic_columns=(), percent_columns=()):
        cells = []
        for index, value in enumerate(values, start=1):
            cell = WriteOnlyCell(self.ws, value=value)
            if header:
                cell.font = _HEADER_FONT
                cell.fill = _HEADER_FILL
            elif index in italic_columns:
                cell.font = _NOT_ANALYZED_FONT
            if index in percent_columns:
                cell.number_format = "0.0%"
            cells.append(cell)
        self.ws.append(cells)
        self.row_count += 1

    def finish(self):
        last_col = get_column_letter(len(self.headers))
        self.ws.auto_filter.ref = f"A1:{last_col}{self.row_count}"


def _placeholder(ws, text) -> None:
    ws.append([text], italic_columns=(1,))


def _target_cell(t: dict) -> str:
    return f"{t.get('name')} ({t.get('phone_number')})"


def _finding_evidence(finding: dict) -> str:
    """A one-cell digest of the finding's evidence -- enough to read the report
    without the app; the full detail stays on screen."""
    ev = finding.get("evidence") or {}
    if finding.get("type") == "mutual_contacts":
        top = sorted(ev.get("shared_contacts") or [],
                     key=lambda c: -(c.get("count_a", 0) + c.get("count_b", 0)))[:5]
        return "; ".join(
            f"{c.get('party')} (A {c.get('count_a')}× / B {c.get('count_b')}×)"
            for c in top)
    if finding.get("type") == "co_presence":
        return "; ".join(
            f"{e.get('area')} {e.get('day')}" for e in (ev.get("events") or [])[:8])
    if finding.get("type") == "direct_contact":
        first, last = ev.get("first") or "—", ev.get("last") or "—"
        return f"first {_fmt_when(first)}, last {_fmt_when(last)}"
    return ""


def _mode_cell(result: dict) -> str:
    """One-cell dataset-mode digest (adaptive gates): the mode changes what the
    mutual-relationship strengths MEAN, so a saved row must carry it. Rows saved
    before the adaptive gates have no dataset_context -> em-dash."""
    ctx = result.get("dataset_context") or {}
    if not ctx.get("mode"):
        return "—"
    return f"{ctx['mode']} ({ctx.get('classification')} confidence)"


def _append_match_rows(ws, saved: dict) -> None:
    result = saved["result"]
    pair = result.get("pair") or {}
    base = [
        saved["id"], saved.get("dataset_name"),
        _target_cell(pair.get("target_a") or {}),
        _target_cell(pair.get("target_b") or {}),
        _fmt_when(saved.get("created_at")),
    ]
    mode = _mode_cell(result)
    findings = result.get("findings") or []
    if not findings:
        caveats = "; ".join(result.get("caveats") or [])
        ws.append(
            base + ["No link found", "—", "", caveats, "", mode, ""],
            italic_columns=(6,),
        )
        return
    for f in findings:
        ws.append(base + [
            f.get("label"), f.get("strength"),
            ", ".join(f.get("bound_by") or []),
            f.get("headline"), _finding_evidence(f),
            mode, "; ".join(f.get("notes") or []),
        ])


_CALL_TYPES = {1: "out call", 2: "in call", 11: "out SMS", 22: "in SMS"}


def _call_type_cell(code) -> str:
    """"wording (code)" -- the app-wide convention (app/web/js/call-types.js)."""
    return f"{_CALL_TYPES.get(code, 'unknown')} ({code})"


def _cap_note(shown: int, total: int) -> str | None:
    if shown >= total:
        return None
    return f"{shown:,} of {total:,} rows shown; listing capped"


def _append_ledger_rows(ws, saved: dict, row_allowance: int) -> int:
    """Stream one saved ledger within its remaining Excel row allowance."""
    if row_allowance <= 0:
        return 0
    pair = saved["pair"]
    pair_cell = (f"{pair['target_a']['name']} ({pair['target_a']['phone_number']}) ↔ "
                 f"{pair['target_b']['name']} ({pair['target_b']['phone_number']})")
    base = [saved["id"], saved.get("dataset_name"), pair_cell,
            _fmt_when(saved.get("created_at"))]
    rows = saved.get("rows") or []
    total = max(saved.get("row_count") or 0, len(rows))
    if not rows:
        note = _cap_note(0, total)
        label = "listing capped" if note else "no records"
        ws.append(
            base + [label] + [""] * (len(LEDGER_HEADERS) - len(base) - 2) + [note or ""],
            italic_columns=(5,),
        )
        return 1

    shown = min(len(rows), row_allowance)
    note = _cap_note(shown, total)
    for index, r in enumerate(rows[:shown]):
        distinctive = r.get("distinctive")
        ws.append(base + [
            r.get("category_label"), r.get("who"), r.get("who_phone"),
            _fmt_when(r.get("timestamp")), _call_type_cell(r.get("call_type")),
            r.get("duration_seconds"),
            r.get("other_party") or "—", r.get("other_party_name") or "—",
            "yes" if r.get("other_party_is_target") else "",
            r.get("area"),
            "—" if distinctive is None else ("distinctive" if distinctive else "common"),
            note if index == 0 and note else "",
        ])
    return shown


def _append_tally_rows(ws, saved: dict) -> None:
    tally = saved["tally"]
    base = [
        saved["id"], saved.get("target_name"), saved.get("phone_number"),
        saved.get("dataset_name"), _fmt_when(saved.get("created_at")),
        saved.get("filter_label"), tally.get("total_records"),
    ]
    top = tally.get("top") or []
    if not top:
        ws.append(base + ["—", "no rankable values", ""], italic_columns=(9,))
        return
    for rank, row in enumerate(top, start=1):
        ws.append(base + [rank, row.get("value"), row.get("count")])


def build_results_workbook(rows: list[dict], pair_matches: list[dict] = (),
                           tallies: list[dict] = (), ledgers=(), *,
                           ledger_count: int | None = None) -> bytes:
    """rows: targets_with_latest_result() output. pair_matches / tallies / ledgers:
    the SAVED items, already JSON-decoded ({"result": …} / {"tally": …} /
    {"rows": […], "pair": {…}})."""
    if ledger_count is None:
        try:
            ledger_count = len(ledgers)
        except TypeError as exc:
            raise ValueError("ledger_count is required for a ledger iterator") from exc

    wb = Workbook(write_only=True)
    summary = _StreamingSheet(wb, "Summary", HEADERS)
    areas_ws = _StreamingSheet(wb, "Frequent areas", AREAS_HEADERS)
    contacts_ws = _StreamingSheet(wb, "Frequent contacts", CONTACTS_HEADERS)
    matches_ws = _StreamingSheet(wb, "Contact matches", MATCHES_HEADERS)
    ledger_ws = _StreamingSheet(wb, "Pair records", LEDGER_HEADERS)
    tallies_ws = _StreamingSheet(wb, "Frequency counts", TALLIES_HEADERS)

    for row in rows:
        base = [row["id"], row["name"], row["phone_number"]]
        if row["result_json"] is None:
            summary.append(
                base + [row["dataset_name"], "not analyzed"] + [""] * 5,
                italic_columns=(5,),
            )
            continue
        payload = json.loads(row["result_json"])
        home = _detection(payload.get("home"))
        work = _detection(payload.get("work"))
        frequent = payload.get("frequent_areas") or []
        summary.append(base + [
            row["dataset_name"], _fmt_when(payload.get("analyzed_at")),
            home[0], home[1], work[0], work[1],
            # .get() (not a['area']) to match the detail-sheet loop below: a
            # partial/legacy frequent_areas entry degrades to a blank cell here
            # instead of KeyError-ing the whole workbook.
            ", ".join(f"{a.get('area')} ({a.get('count')})" for a in frequent),
        ])
        for rank, a in enumerate(frequent, start=1):
            areas_ws.append(
                base + [rank, a.get("area"), a.get("count"), a.get("share")],
                percent_columns=(7,),
            )
        for c in payload.get("frequent_contacts") or []:
            contacts_ws.append(base + [c.get("number"), c.get("total"),
                                       c.get("call_out"), c.get("call_in"),
                                       c.get("sms_out"), c.get("sms_in")])

    for saved in pair_matches:
        _append_match_rows(matches_ws, saved)
    if not pair_matches:
        _placeholder(matches_ws, "none saved")
    remaining_rows = LEDGER_EXPORT_ROW_BUDGET
    remaining_ledgers = ledger_count
    for saved in ledgers:
        remaining_ledgers -= 1
        # Reserve one row for each later ledger so aggregate truncation remains
        # disclosed per ledger instead of silently dropping a saved item.
        allowance = max(0, remaining_rows - remaining_ledgers)
        used = _append_ledger_rows(ledger_ws, saved, allowance)
        remaining_rows -= used
    if ledger_count == 0:
        _placeholder(ledger_ws, "none saved")
    for saved in tallies:
        _append_tally_rows(tallies_ws, saved)
    if not tallies:
        _placeholder(tallies_ws, "none saved")

    for ws in (summary, areas_ws, contacts_ws, matches_ws, ledger_ws, tallies_ws):
        ws.finish()
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
