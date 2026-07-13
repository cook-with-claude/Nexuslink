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
"Pair records" the EXHAUSTIVE record ledger of each SAVED pair (every call and
every shared-area record, with dates/times -- no cap, and no confidence: these are
records, not verdicts); "Frequency counts" one row per ranked value of each SAVED
explorer tally. The staged sheets are click-to-save: nothing lands automatically.
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
MATCHES_HEADERS = ["Match ID", "Dataset", "Target A", "Target B", "Saved at",
                   "Finding", "Strength", "Bound by", "Headline", "Key evidence",
                   "Dataset mode", "Near-boundary notes"]
TALLIES_HEADERS = ["Count ID", "Target", "Phone number", "Dataset", "Saved at",
                   "Filters", "Total records", "Rank", "Value", "Count"]
# The pair record ledger (spec 2026-07-13-pair-record-ledger-design): the actual
# records behind a pair, EXHAUSTIVE -- no cap, that is the point of the sheet. No
# confidence column: these are records, not verdicts.
LEDGER_HEADERS = ["Ledger ID", "Dataset", "Pair", "Saved at", "Category", "Who",
                  "Phone", "Date & time", "Call type", "Duration (s)",
                  "Other party", "Other party name", "Also a target", "Area",
                  "Distinctive"]

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


def _placeholder(ws, text) -> None:
    ws.append([text])
    ws.cell(row=ws.max_row, column=1).font = _NOT_ANALYZED_FONT


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
        ws.append(base + ["No link found", "—", "", caveats, "", mode, ""])
        ws.cell(row=ws.max_row, column=6).font = _NOT_ANALYZED_FONT
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


def _append_ledger_rows(ws, saved: dict) -> None:
    """EVERY record of one saved ledger -- no cap. The on-screen table pages at 50
    rows; the workbook is where the exhaustive listing lives.

    `distinctive` is None for direct rows (the pair themselves are not a "shared"
    item to judge), so it renders as an em-dash rather than a misleading "no".
    """
    pair = saved["pair"]
    pair_cell = (f"{pair['target_a']['name']} ({pair['target_a']['phone_number']}) ↔ "
                 f"{pair['target_b']['name']} ({pair['target_b']['phone_number']})")
    base = [saved["id"], saved.get("dataset_name"), pair_cell,
            _fmt_when(saved.get("created_at"))]
    rows = saved.get("rows") or []
    if not rows:
        ws.append(base + ["no records"] + [""] * (len(LEDGER_HEADERS) - len(base) - 1))
        ws.cell(row=ws.max_row, column=5).font = _NOT_ANALYZED_FONT
        return
    for r in rows:
        distinctive = r.get("distinctive")
        ws.append(base + [
            r.get("category_label"), r.get("who"), r.get("who_phone"),
            _fmt_when(r.get("timestamp")), _call_type_cell(r.get("call_type")),
            r.get("duration_seconds"),
            r.get("other_party") or "—", r.get("other_party_name") or "—",
            "yes" if r.get("other_party_is_target") else "",
            r.get("area"),
            "—" if distinctive is None else ("distinctive" if distinctive else "common"),
        ])


def _append_tally_rows(ws, saved: dict) -> None:
    tally = saved["tally"]
    base = [
        saved["id"], saved.get("target_name"), saved.get("phone_number"),
        saved.get("dataset_name"), _fmt_when(saved.get("created_at")),
        saved.get("filter_label"), tally.get("total_records"),
    ]
    top = tally.get("top") or []
    if not top:
        ws.append(base + ["—", "no rankable values", ""])
        ws.cell(row=ws.max_row, column=9).font = _NOT_ANALYZED_FONT
        return
    for rank, row in enumerate(top, start=1):
        ws.append(base + [rank, row.get("value"), row.get("count")])


def build_results_workbook(rows: list[dict], pair_matches: list[dict] = (),
                           tallies: list[dict] = (), ledgers: list[dict] = ()) -> bytes:
    """rows: targets_with_latest_result() output. pair_matches / tallies / ledgers:
    the SAVED items, already JSON-decoded ({"result": …} / {"tally": …} /
    {"rows": […], "pair": {…}})."""
    wb = Workbook()
    summary = wb.active
    summary.title = "Summary"
    areas_ws = wb.create_sheet("Frequent areas")
    contacts_ws = wb.create_sheet("Frequent contacts")
    matches_ws = wb.create_sheet("Contact matches")
    ledger_ws = wb.create_sheet("Pair records")
    tallies_ws = wb.create_sheet("Frequency counts")
    summary.append(HEADERS)
    areas_ws.append(AREAS_HEADERS)
    contacts_ws.append(CONTACTS_HEADERS)
    matches_ws.append(MATCHES_HEADERS)
    ledger_ws.append(LEDGER_HEADERS)
    tallies_ws.append(TALLIES_HEADERS)

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
            # .get() (not a['area']) to match the detail-sheet loop below: a
            # partial/legacy frequent_areas entry degrades to a blank cell here
            # instead of KeyError-ing the whole workbook.
            ", ".join(f"{a.get('area')} ({a.get('count')})" for a in frequent),
        ])
        for rank, a in enumerate(frequent, start=1):
            areas_ws.append(base + [rank, a.get("area"), a.get("count"), a.get("share")])
            areas_ws.cell(row=areas_ws.max_row, column=7).number_format = "0.0%"
        for c in payload.get("frequent_contacts") or []:
            contacts_ws.append(base + [c.get("number"), c.get("total"),
                                       c.get("call_out"), c.get("call_in"),
                                       c.get("sms_out"), c.get("sms_in")])

    for saved in pair_matches:
        _append_match_rows(matches_ws, saved)
    if not pair_matches:
        _placeholder(matches_ws, "none saved")
    for saved in ledgers:
        _append_ledger_rows(ledger_ws, saved)
    if not ledgers:
        _placeholder(ledger_ws, "none saved")
    for saved in tallies:
        _append_tally_rows(tallies_ws, saved)
    if not tallies:
        _placeholder(tallies_ws, "none saved")

    for ws in (summary, areas_ws, contacts_ws, matches_ws, ledger_ws, tallies_ws):
        _finish_sheet(ws)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
