"""Generate the contact-matcher test datasets, verified against the REAL engine.

Two workbooks land in the repo root:

- sample_matcher_scenarios.xlsx   -- a STRANGERS-mode dataset (40 subscribers)
  whose pairs P01-P15 exercise every finding type at every strength, every gate
  as the binding gate, the commonality discount + floor, the disjoint-window
  caveat, the shared-area detail row, and no-link.
- sample_matcher_closeknit.xlsx   -- a CLOSE-KNIT-mode dataset (12 subscribers,
  everyone shares the same 8 community contacts): any ordinary pair rates
  Medium (real mutuals, group-wide fabric), and one standout pair (members 11
  and 12) shares 3 rare private mutuals and rates High.

Every expected outcome is asserted against app.matching.service.compute_match
(and every row against the import validator) BEFORE a workbook is written, so
the files and docs/matcher-test-scenarios.md cannot drift from the engine
without this script failing. Rerun after any gate/threshold change:

    .venv\\Scripts\\python.exe tools\\gen_matcher_scenarios.py
"""
from __future__ import annotations

import pathlib
import sqlite3
import sys

REPO = str(pathlib.Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO)

from app.datasets.validation import validate_row  # noqa: E402
from app.matching import service  # noqa: E402
from phase1_cdr.loader import REQUIRED_COLUMNS  # noqa: E402


class Dataset:
    def __init__(self, name):
        self.name = name
        self.rows: list[dict] = []

    def add(self, phone, day, hh, mm, area, ctype, other, dur=120):
        self.rows.append({
            "phone_number": phone,
            "imei": "35" + phone[-7:],
            "area": area,
            "timestamp": f"2026-05-{day:02d}T{hh:02d}:{mm:02d}:00",
            "call_type": ctype,
            "duration_seconds": dur if ctype in (1, 2) else 0,
            "other_party": other,
            "other_imei": "",
            "other_area": "",
        })

    def own_traffic(self, phone, area, contacts, n, days=None, hour0=8):
        """n filler records cycling the subscriber's own contacts. Days cycle a
        list that starts [first, last] so the span covers the window."""
        days = days or [1, 30] + list(range(2, 30))
        for i in range(n):
            day = days[i % len(days)]
            self.add(phone, day, hour0 + (i % 9), (i * 7) % 60, area,
                     1 if i % 4 else 11, contacts[i % len(contacts)])

    def shared_traffic(self, pa, pb, parties, rows_each_side_per_party, days=None):
        days = days or list(range(1, 29))
        for j, party in enumerate(parties):
            for i in range(rows_each_side_per_party):
                d = days[(j * rows_each_side_per_party + i) % len(days)]
                self.add(pa, d, 9 + (i % 8), (j * 11 + i * 3) % 60, home(pa), 1, party)
                self.add(pb, d, 9 + (i % 8), (j * 13 + i * 5) % 60, home(pb), 1, party)

    def co_events(self, pa, pb, area, days, hh=10, gap_min=30):
        """One meet-up event per day: both subscribers in `area` within gap_min."""
        for d in days:
            self.add(pa, d, hh, 0, area, 1, f"666{pa[-4:]}1")
            self.add(pb, d, hh, gap_min, area, 1, f"666{pb[-4:]}1")


def home(phone):
    return f"HOME_{phone}"


def own_contacts(phone, k):
    return [f"666{phone[-4:]}{i}" for i in range(1, k + 1)]


HUBS = [f"888000{i}" for i in range(1, 6)]  # dataset-common contact hubs


# ================================================================ strangers ==
def build_strangers() -> Dataset:
    ds = Dataset("strangers")
    add, own, shared, co = ds.add, ds.own_traffic, ds.shared_traffic, ds.co_events

    # P01 -- everything High: heavy two-way direct, 5 distinctive shared
    # contacts, 6 meet-up days in a private cafe.
    A, B = "5550101", "5550102"
    for i, d in enumerate((2, 6, 10, 14, 18, 22)):
        add(A, d, 20, 5, home(A), 1 if i < 4 else 11, B)   # A -> B
        add(B, d, 21, 5, home(B), 1 if i < 4 else 11, A)   # B -> A
    shared(A, B, [f"777010{i}" for i in range(1, 6)], 3)
    own(A, home(A), own_contacts(A, 5), 23)
    own(B, home(B), own_contacts(B, 5), 23)
    co(A, B, "P01_CAFE", (3, 7, 11, 15, 19, 23))

    # P02 -- direct only, High, both directions; nothing else shared.
    A, B = "5550201", "5550202"
    for i in range(7):
        add(A, 2 + i * 4, 19, 10, home(A), 1 if i < 5 else 11, B)
    for i in range(5):
        add(B, 3 + i * 5, 19, 40, home(B), 1 if i < 4 else 11, A)
    own(A, home(A), own_contacts(A, 5), 45)
    own(B, home(B), own_contacts(B, 5), 47)

    # P03 -- direct Medium, A -> B only (5 records).
    A, B = "5550301", "5550302"
    for i in range(5):
        add(A, 4 + i * 5, 18, 0, home(A), 1 if i < 3 else 11, B)
    own(A, home(A), own_contacts(A, 5), 47)
    own(B, home(B), own_contacts(B, 5), 52)

    # P04 -- direct Low, B -> A only (2 records; carries a "just short of
    # Medium" cliff note by design).
    A, B = "5550401", "5550402"
    add(B, 9, 17, 30, home(B), 1, A)
    add(B, 21, 17, 30, home(B), 11, A)
    own(A, home(A), own_contacts(A, 5), 52)
    own(B, home(B), own_contacts(B, 5), 50)

    # P05 -- mutual only, all gates High (5 distinctive shared of 10-circles).
    A, B = "5550501", "5550502"
    shared(A, B, [f"777050{i}" for i in range(1, 6)], 4)
    own(A, home(A), own_contacts(A, 5), 30)
    own(B, home(B), own_contacts(B, 5), 30)

    # P06 -- mutual Medium bound by OVERLAP SHARE (3 shared / 10-circles).
    A, B = "5550601", "5550602"
    shared(A, B, [f"777060{i}" for i in range(1, 4)], 4)
    own(A, home(A), own_contacts(A, 7), 42)
    own(B, home(B), own_contacts(B, 7), 42)

    # P07 -- mutual Low bound by DISTINCTIVENESS (5 hubs + 2 distinctive = 2/7).
    A, B = "5550701", "5550702"
    shared(A, B, HUBS + ["7770701", "7770702"], 4)
    own(A, home(A), own_contacts(A, 3), 24)
    own(B, home(B), own_contacts(B, 3), 24)

    # P08 -- mutual SUPPRESSED by the commonality discount (3 hubs + only 1
    # distinctive shared -> below MUTUAL_MIN_DISTINCTIVE, no findings at all).
    A, B = "5550801", "5550802"
    shared(A, B, HUBS[:3] + ["7770801"], 3)
    own(A, home(A), own_contacts(A, 6), 38)
    own(B, home(B), own_contacts(B, 6), 38)

    # P09 -- co-presence only, all gates High (6 meet-ups in a private park).
    A, B = "5550901", "5550902"
    co(A, B, "P09_PARK", (4, 8, 12, 16, 20, 24))
    own(A, home(A), own_contacts(A, 5), 46)
    own(B, home(B), own_contacts(B, 5), 46)

    # P10 -- co-presence Medium bound by EVENT COUNT (3 meet-up days).
    A, B = "5551001", "5551002"
    co(A, B, "P10_GYM", (5, 12, 19))
    own(A, home(A), own_contacts(A, 5), 49)
    own(B, home(B), own_contacts(B, 5), 49)

    # P11 -- co-presence Low bound by LOCATION DISTINCTIVENESS (5 meet-ups,
    # all in the dataset-common MALL).
    A, B = "5551101", "5551102"
    co(A, B, "MALL", (3, 9, 15, 21, 27), hh=18)
    own(A, home(A), own_contacts(A, 5), 47)
    own(B, home(B), own_contacts(B, 5), 47)

    # P12 -- SAMPLE gate binds: the second subscriber has only 10 records.
    A, B = "5551201", "5551202"
    for j, party in enumerate(("7771201", "7771202")):
        for i in range(4):
            add(A, 5 * (j * 4 + i + 1) % 28 + 1, 9 + i, 15, home(A), 1, party)
        for d in (5 + 10 * j, 15 + 10 * j):
            add(B, d, 9, 20, home(B), 1, party)
    co(A, B, "P12_DOCK", (6, 13))
    own(A, home(A), own_contacts(A, 5), 40)
    for d in (1, 3, 27, 30):
        add(B, d, 8, 0, home(B), 1, own_contacts(B, 1)[0])

    # P13 -- disjoint observation windows: A seen May 1-14, B seen May 16-30.
    A, B = "5551301", "5551302"
    days_a = [1, 14] + list(range(2, 14))
    days_b = [16, 30] + list(range(17, 30))
    for j, party in enumerate([f"777130{i}" for i in range(1, 4)]):
        for i in range(5):
            add(A, days_a[(j * 5 + i) % len(days_a)], 9 + i, 10, home(A), 1, party)
            add(B, days_b[(j * 5 + i) % len(days_b)], 9 + i, 40, home(B), 1, party)
    own(A, home(A), own_contacts(A, 3), 36, days=days_a)
    own(B, home(B), own_contacts(B, 3), 36, days=days_b)

    # P14 -- no link at all.
    A, B = "5551401", "5551402"
    own(A, home(A), own_contacts(A, 5), 52)
    own(B, home(B), own_contacts(B, 5), 52)

    # P15 -- shared area WITHOUT time overlap (always hours apart).
    A, B = "5551501", "5551502"
    for d in (2, 9, 16, 23):
        add(A, d, 9, 0, "P15_STADIUM", 1, own_contacts(A, 1)[0])
        add(B, d, 15, 0, "P15_STADIUM", 1, own_contacts(B, 1)[0])
    own(A, home(A), own_contacts(A, 5), 48)
    own(B, home(B), own_contacts(B, 5), 48)

    # Fillers F01-F10 -- make the hubs and MALL dataset-common (>= the 20% x 38
    # = 7.6-subscriber cutoff for every tested pair; the floor of 3 is far
    # exceeded, so this dataset exercises the PERCENTAGE arm of the rule).
    for n in range(1, 11):
        f = f"55599{n:02d}"
        for j, hub in enumerate(HUBS):
            add(f, 2 + n + j * 4, 10 + j, n % 60, home(f), 1, hub)
            add(f, 3 + n + j * 4, 11 + j, n % 60, home(f), 11, hub)
        for d in (5, 14, 25):
            add(f, d, 12, (n * 5) % 60, "MALL", 1, HUBS[0])
        ds.own_traffic(f, home(f), own_contacts(f, 3), 8)
    return ds


STRANGERS_PAIRS = {f"P{i:02d}": (f"555{i:02d}01", f"555{i:02d}02")
                   for i in range(1, 16)}
# scenario -> {finding_type: (strength, bound_by-or-None)}
STRANGERS_EXPECT = {
    "P01": {"direct_contact": ("High", None), "mutual_contacts": ("High", None),
            "co_presence": ("High", None)},
    "P02": {"direct_contact": ("High", None)},
    "P03": {"direct_contact": ("Medium", None)},
    "P04": {"direct_contact": ("Low", None)},
    "P05": {"mutual_contacts": ("High", None)},
    "P06": {"mutual_contacts": ("Medium", ["overlap share"])},
    "P07": {"mutual_contacts": ("Low", ["distinctiveness"])},
    "P08": {},  # suppressed -> no findings
    "P09": {"co_presence": ("High", None)},
    "P10": {"co_presence": ("Medium", ["event count"])},
    "P11": {"co_presence": ("Low", ["location distinctiveness"])},
    "P12": {"mutual_contacts": ("Low", ["sample"]), "co_presence": ("Low", ["sample"])},
    "P13": {"mutual_contacts": ("Low", ["window overlap"])},
    "P14": {},
    "P15": {},
}
STRANGERS_CAVEAT = {"P13"}
STRANGERS_SHARED_AREA = {"P15": ["P15_STADIUM"]}


# =============================================================== close-knit ==
FABRIC = [f"444500{i}" for i in range(1, 9)]       # the whole group's contacts
RARE = ["4446001", "4446002", "4446003"]           # only members 11+12


def build_closeknit() -> Dataset:
    """12 clique members. Everyone calls the same 8 community contacts, so ANY
    pair shares 8 contacts -- in strangers rules that would all be discounted
    (or suppress the finding); close-knit mode rates it Medium. Members 11+12
    additionally share 3 rare private mutuals -> High."""
    ds = Dataset("closeknit")
    members = [f"44400{i:02d}" for i in range(1, 13)]
    for m, phone in enumerate(members, start=1):
        personal = [f"4447{m:02d}{j}" for j in (1, 2)]
        if m in (11, 12):
            for j, party in enumerate(RARE):
                for i in range(3):
                    ds.add(phone, 3 + j * 9 + i * 3, 18 + j, (m * 7 + i) % 60,
                           home(phone), 1, party)
            ds.own_traffic(phone, home(phone), FABRIC, 40)
            ds.own_traffic(phone, home(phone), personal, 8, hour0=13)
        else:
            ds.own_traffic(phone, home(phone), FABRIC, 40)
            ds.own_traffic(phone, home(phone), personal, 16, hour0=13)
    return ds


CLOSEKNIT_PAIRS = {
    "CK-ordinary": ("4440001", "4440002"),
    "CK-cross": ("4440003", "4440007"),
    "CK-standout": ("4440011", "4440012"),
}
CLOSEKNIT_EXPECT = {
    "CK-ordinary": {"mutual_contacts": ("Medium", ["distinctiveness"])},
    "CK-cross": {"mutual_contacts": ("Medium", ["distinctiveness"])},
    "CK-standout": {"mutual_contacts": ("High", None)},
}


# ============================================================= verification ==
def verify(ds: Dataset, pairs, expect, expect_mode,
           caveat_pairs=frozenset(), shared_area=None):
    bad = [(r, reason) for r in ds.rows
           for _, reason in [validate_row(r)] if reason is not None]
    if bad:
        for r, reason in bad[:5]:
            print("INVALID ROW:", reason, r)
        sys.exit(f"{ds.name}: {len(bad)} rows fail import validation")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE cdr_records (dataset_id INTEGER, phone_number TEXT, imei TEXT,"
        " area TEXT, timestamp TEXT, call_type INTEGER, duration_seconds INTEGER,"
        " other_party TEXT, other_imei TEXT, other_area TEXT)")
    conn.executemany(
        "INSERT INTO cdr_records VALUES (1, :phone_number, :imei, :area, :timestamp,"
        " :call_type, :duration_seconds, :other_party, :other_imei, :other_area)",
        [{**r, "other_party": r["other_party"] or None} for r in ds.rows])

    n_users = conn.execute(
        "SELECT COUNT(DISTINCT phone_number) n FROM cdr_records").fetchone()["n"]
    failures, summary = [], []
    mode_line = None
    for scen, (pa, pb) in pairs.items():
        ta = {"id": 1, "name": f"{scen}-A", "dataset_id": 1, "phone_number": pa}
        tb = {"id": 2, "name": f"{scen}-B", "dataset_id": 1, "phone_number": pb}
        result = service.compute_match(conn, ta, tb)
        ctx = result["dataset_context"]
        mode_line = (f"{ctx['mode']} ({ctx['classification']}, "
                     f"avg {ctx['avg_shared_contacts_per_pair']} shared/pair)")
        if ctx["mode"] != expect_mode:
            failures.append(f"{scen}: dataset mode {ctx['mode']}, expected {expect_mode}")
        got = {f["type"]: f for f in result["findings"]}
        exp = expect[scen]
        for ftype, (strength, bound) in exp.items():
            if ftype not in got:
                failures.append(f"{scen}: expected {ftype}, finding absent")
                continue
            if got[ftype]["strength"] != strength:
                failures.append(
                    f"{scen}: {ftype} strength {got[ftype]['strength']!r}, expected "
                    f"{strength!r} (bound_by={got[ftype]['bound_by']})")
            if bound is not None and got[ftype]["bound_by"] != bound:
                failures.append(f"{scen}: {ftype} bound_by {got[ftype]['bound_by']},"
                                f" expected {bound}")
        for ftype in got:
            if ftype not in exp:
                failures.append(f"{scen}: unexpected finding {ftype} "
                                f"({got[ftype]['strength']}, {got[ftype]['bound_by']})")
        if scen in caveat_pairs and not any("overlap only" in c for c in result["caveats"]):
            failures.append(f"{scen}: expected a window caveat, none present")
        want_detail = (shared_area or {}).get(scen, [])
        if result["details"]["shared_areas_no_time_overlap"] != want_detail:
            failures.append(
                f"{scen}: shared-areas detail "
                f"{result['details']['shared_areas_no_time_overlap']},"
                f" expected {want_detail}")
        if not exp and not result["no_link"]:
            failures.append(f"{scen}: expected no_link")
        parts = [f"{t.split('_')[0]} {f['strength']} [{', '.join(f['bound_by'])}]"
                 for t, f in got.items()] or (
            ["no link" + (" + shared-area detail" if want_detail else "")])
        summary.append(f"{scen:<12} {pa} vs {pb:<9} -> {'; '.join(parts)}")

    print(f"\n== {ds.name}: {len(ds.rows)} rows, {n_users} subscribers, "
          f"mode {mode_line} ==")
    for s in summary:
        print(s)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)


def write_xlsx(ds: Dataset, path: str):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "cdr"
    ws.append(REQUIRED_COLUMNS)
    for r in sorted(ds.rows, key=lambda r: (r["timestamp"], r["phone_number"])):
        ws.append([r[c] for c in REQUIRED_COLUMNS])
    wb.save(path)
    print(f"wrote {path} ({len(ds.rows)} rows)")


if __name__ == "__main__":
    strangers = build_strangers()
    verify(strangers, STRANGERS_PAIRS, STRANGERS_EXPECT, "strangers",
           STRANGERS_CAVEAT, STRANGERS_SHARED_AREA)
    closeknit = build_closeknit()
    verify(closeknit, CLOSEKNIT_PAIRS, CLOSEKNIT_EXPECT, "close-knit")
    write_xlsx(strangers, REPO + r"\sample_matcher_scenarios.xlsx")
    write_xlsx(closeknit, REPO + r"\sample_matcher_closeknit.xlsx")
    print("OK")
