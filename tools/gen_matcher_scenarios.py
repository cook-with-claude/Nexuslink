"""Generate the contact-matcher test datasets, verified against the REAL engine.

Two workbooks land in the repo root:

- sample_matcher_scenarios.xlsx   -- a STRANGERS-mode dataset (40 subscribers)
  whose pairs P01-P15 exercise every finding type at every strength, every gate
  as the binding gate, the commonality discount + floor, the disjoint-window
  caveat, the shared-area detail row, and no-link.
- sample_matcher_closeknit.xlsx   -- a CLOSE-KNIT-mode dataset (12 subscribers,
  overlapping six-member community circles): reviewed ordinary pairs each have
  one pair-specific mutual and rate Medium, while members 11 and 12 share 3 rare
  private mutuals and rate High. No ubiquitous hub drives the mode or a finding.

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

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

STRANGERS_OUTPUT = REPO_ROOT / "sample_matcher_scenarios.xlsx"
CLOSEKNIT_OUTPUT = REPO_ROOT / "sample_matcher_closeknit.xlsx"

from app.datasets.validation import validate_row  # noqa: E402
from app.infra.phase1 import REQUIRED_COLUMNS  # noqa: E402
from app.matching import gates, repo, service  # noqa: E402


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
FABRIC_A = [f"44451{i:02d}" for i in range(1, 6)]   # members 1-6
FABRIC_B = [f"44452{i:02d}" for i in range(1, 6)]   # members 7-12
BRIDGES = [f"44453{i:02d}" for i in range(1, 5)]    # members 3/4/5 + 7/8/9
ORDINARY_RARE = "4446001"                          # only members 1+2
CROSS_RARE = "4446002"                             # only members 3+7
STANDOUT_RARE = ["4446011", "4446012", "4446013"]  # only members 11+12


def build_closeknit() -> Dataset:
    """12 members connected by non-hub six-person community contacts."""
    ds = Dataset("closeknit")
    members = [f"44400{i:02d}" for i in range(1, 13)]
    for m, phone in enumerate(members, start=1):
        contacts = list(FABRIC_A if m <= 6 else FABRIC_B)
        if m in (3, 4, 5, 7, 8, 9):
            contacts.extend(BRIDGES)
        if m in (1, 2):
            contacts.append(ORDINARY_RARE)
        if m in (3, 7):
            contacts.append(CROSS_RARE)
        if m in (11, 12):
            contacts.extend(STANDOUT_RARE)
        personal = [f"4447{m:02d}{j}" for j in (1, 2)]
        ds.own_traffic(phone, home(phone), contacts, 50)
        ds.own_traffic(phone, home(phone), personal, 10, hour0=13)
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


# =============================================== isolated hardening scenarios ==
# Dataset-level cases cannot coexist in one workbook: a five-subscriber small-N
# population and a 100-subscriber hub population are mutually exclusive facts.
# They still run through the real engine before either workbook is written.
def build_hub_flip():
    ds = Dataset("hub-flip")
    services = ["9009001", "9009002", "9009003"]
    phones = [f"901{i:04d}" for i in range(100)]
    for index, phone in enumerate(phones):
        for offset, service_number in enumerate(services):
            ds.add(phone, 2 + offset, 9 + offset, index % 60,
                   home(phone), 1, service_number)
    return ds, phones[0], phones[1]


def build_double_sided_direct():
    ds = Dataset("double-sided-direct")
    phone_a, phone_b = "9020001", "9020002"
    for index, day in enumerate((2, 6, 10, 14, 18)):
        call_type = 1 if index < 4 else 11
        incoming_type = 2 if call_type == 1 else 22
        ds.add(phone_a, day, 10, 0, home(phone_a), call_type, phone_b)
        ds.add(phone_b, day, 10, 0, home(phone_b), incoming_type, phone_a)
    return ds, phone_a, phone_b


def build_location_heavy_sample():
    ds = Dataset("location-heavy-sample")
    phone_a, phone_b = "9030001", "9030002"
    for offset, party in enumerate(("9039001", "9039002")):
        ds.add(phone_a, 1 + offset, 9, 0, home(phone_a), 1, party)
        ds.add(phone_b, 1 + offset, 10, 0, home(phone_b), 1, party)
    for index in range(48):
        day = 3 + index % 26
        ds.add(phone_a, day, 8 + index % 10, index % 60,
               home(phone_a), 1, None)
        ds.add(phone_b, day, 8 + index % 10, index % 60,
               home(phone_b), 1, None)
    # A realistic surrounding population: without it n=2 makes the pair's own two
    # shared contacts look 100%-ubiquitous, and conditional counting reads the
    # degenerate dataset as close-knit. Each filler holds only personal (k=1,
    # non-shared) contacts, so the dataset stays decisively strangers and the
    # scenario keeps testing the sample gate, not the mode.
    for index in range(12):
        filler = f"9031{index:03d}"
        ds.own_traffic(filler, home(filler), own_contacts(filler, 2), 6)
    return ds, phone_a, phone_b


def build_even_median_spread():
    ds = Dataset("even-median-spread")
    phones = [f"904{i:04d}" for i in range(100)]
    for index, phone in enumerate(phones):
        for offset, hub in enumerate(("9049001", "9049002")):
            ds.add(phone, 2 + offset, 8 + offset, index % 60, home(phone), 1, hub)
    for rare in ("9049101", "9049102"):
        ds.add(phones[0], 5, 10, 0, home(phones[0]), 1, rare)
        ds.add(phones[1], 5, 11, 0, home(phones[1]), 1, rare)
    ds.own_traffic(phones[0], home(phones[0]), own_contacts(phones[0], 2), 20)
    ds.own_traffic(phones[1], home(phones[1]), own_contacts(phones[1], 2), 20)
    return ds, phones[0], phones[1]


def build_small_n_cap():
    ds = Dataset("small-N-cap")
    phone_a, phone_b = "9050001", "9050002"
    shared = ["9059001", "9059002"]
    ds.own_traffic(phone_a, home(phone_a), shared, 50)
    ds.own_traffic(phone_b, home(phone_b), shared, 50)
    for index in range(3):
        phone = f"905001{index}"
        ds.own_traffic(phone, home(phone), own_contacts(phone, 2), 20)
    return ds, phone_a, phone_b


def build_midnight_straddle():
    ds = Dataset("midnight-straddle")
    phone_a, phone_b = "9060001", "9060002"
    ds.add(phone_a, 1, 23, 40, "NIGHT_CAFE", 1, "9069001")
    ds.add(phone_a, 2, 0, 20, "NIGHT_CAFE", 1, "9069001")
    ds.add(phone_b, 1, 23, 50, "NIGHT_CAFE", 1, "9069002")
    ds.add(phone_b, 2, 0, 10, "NIGHT_CAFE", 1, "9069002")
    return ds, phone_a, phone_b


def build_two_meetings_one_day():
    ds = Dataset("two-meetings-one-day")
    phone_a, phone_b = "9070001", "9070002"
    for hour in (9, 18):
        ds.add(phone_a, 8, hour, 0, "DAY_CAFE", 1, "9079001")
        ds.add(phone_b, 8, hour, 10, "DAY_CAFE", 1, "9079002")
    return ds, phone_a, phone_b


def _build_family(n_members, hub_count):
    """A hub-and-spoke family: every member calls `hub_count` near-universal
    numbers (mom/dad/group chat) plus two personal contacts. With >= 2 hubs the
    conditional count treats them as group fabric (close-knit); with 1 the
    MANY_MIN=2 floor drops it (strangers). Members 1 and 2 are the compared pair."""
    ds = Dataset(f"family-{hub_count}hub")
    members = [f"908{i:04d}" for i in range(n_members)]
    hubs = [f"9089{h:03d}" for h in range(hub_count)]
    for m, phone in enumerate(members):
        contacts = list(hubs) + [f"9088{m:02d}{j}" for j in (1, 2)]
        ds.own_traffic(phone, home(phone), contacts, 40)
    return ds, members[0], members[1]


def build_family_two_hubs():
    return _build_family(8, 2)


def build_family_one_hub():
    return _build_family(8, 1)


# ============================================================= verification ==
def _connection(ds: Dataset):
    bad = [(r, reason) for r in ds.rows
           for _, reason in [validate_row(r)] if reason is not None]
    if bad:
        for r, reason in bad[:5]:
            print("INVALID ROW:", reason, r)
        sys.exit(f"{ds.name}: {len(bad)} rows fail import validation")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE cdr_records (id INTEGER PRIMARY KEY, dataset_id INTEGER, "
        "phone_number TEXT, imei TEXT, area TEXT, timestamp TEXT, call_type INTEGER, "
        "duration_seconds INTEGER, other_party TEXT, other_imei TEXT, other_area TEXT)")
    conn.executemany(
        "INSERT INTO cdr_records (dataset_id, phone_number, imei, area, timestamp, "
        "call_type, duration_seconds, other_party, other_imei, other_area) "
        "VALUES (1, :phone_number, :imei, :area, :timestamp, :call_type, "
        ":duration_seconds, :other_party, :other_imei, :other_area)",
        [{**r, "other_party": r["other_party"] or None} for r in ds.rows])
    return conn


def _compute(conn, scenario, phone_a, phone_b):
    target_a = {
        "id": 1, "name": f"{scenario}-A", "dataset_id": 1,
        "phone_number": phone_a,
    }
    target_b = {
        "id": 2, "name": f"{scenario}-B", "dataset_id": 1,
        "phone_number": phone_b,
    }
    return service.compute_match(conn, target_a, target_b)


def verify_hardening_scenarios():
    failures = []

    def check(condition, message):
        if not condition:
            failures.append(message)

    def findings(result):
        return {finding["type"]: finding for finding in result["findings"]}

    cases = [
        ("hub-flip", build_hub_flip),
        ("double-sided-direct", build_double_sided_direct),
        ("location-heavy-sample", build_location_heavy_sample),
        ("even-median-spread", build_even_median_spread),
        ("small-N-cap", build_small_n_cap),
        ("midnight-straddle", build_midnight_straddle),
        ("two-meetings-one-day", build_two_meetings_one_day),
        ("family-two-hubs", build_family_two_hubs),
        ("family-one-hub", build_family_one_hub),
    ]
    for scenario, builder in cases:
        ds, phone_a, phone_b = builder()
        conn = _connection(ds)
        result = _compute(conn, scenario, phone_a, phone_b)
        got = findings(result)

        if scenario == "hub-flip":
            check(result["dataset_context"]["mode"] == "strangers",
                  "hub-flip: ubiquitous services changed the dataset to close-knit")
            check("mutual_contacts" not in got,
                  "hub-flip: hub-only overlap produced a mutual finding")
        elif scenario == "double-sided-direct":
            direct = got.get("direct_contact")
            check(direct is not None, "double-sided-direct: direct finding absent")
            if direct:
                evidence = direct["evidence"]
                check(direct["strength"] == "Medium",
                      f"double-sided-direct: strength {direct['strength']}, expected Medium")
                check((evidence["total"], evidence["calls"], evidence["sms"]) == (5, 4, 1),
                      f"double-sided-direct: deduped counts are {evidence}")
                check((evidence["a_to_b"], evidence["b_to_a"]) == (5, 0),
                      f"double-sided-direct: direction split is {evidence}")
        elif scenario == "location-heavy-sample":
            mutual = got.get("mutual_contacts")
            check(mutual is not None, "location-heavy-sample: mutual finding absent")
            if mutual:
                check(mutual["evidence"]["gates"]["sample"] == "Low",
                      "location-heavy-sample: location pings inflated mutual sample")
                check("sample" in mutual["bound_by"],
                      f"location-heavy-sample: bound_by {mutual['bound_by']}")
        elif scenario == "even-median-spread":
            mode_facts = repo.dataset_interconnectedness(
                conn, 1, gates.MEGA_POPULAR_FRACTION,
                gates.MEGA_POPULAR_MANY_MIN, gates.MEGA_POPULAR_MANY_FRACTION)
            check(mode_facts["contact_spread_median"] == 51,
                  f"even-median-spread: median {mode_facts['contact_spread_median']}")
        elif scenario == "family-two-hubs":
            check(result["dataset_context"]["mode"] == "close-knit",
                  "family-two-hubs: 2 universal family hubs did NOT read close-knit "
                  "(the bug the conditional count fixes)")
        elif scenario == "family-one-hub":
            check(result["dataset_context"]["mode"] == "strangers",
                  "family-one-hub: a single universal hub flipped the dataset "
                  "(the MANY_MIN=2 floor should keep it strangers)")
        elif scenario == "small-N-cap":
            mutual = got.get("mutual_contacts")
            check(mutual is not None, "small-N-cap: mutual finding absent")
            if mutual:
                check(mutual["strength"] == "Medium",
                      f"small-N-cap: strength {mutual['strength']}, expected Medium")
                check(mutual["bound_by"] == ["comparison population"],
                      f"small-N-cap: bound_by {mutual['bound_by']}")
        elif scenario == "midnight-straddle":
            events = got["co_presence"]["evidence"]["events"]
            check(len(events) == 1,
                  f"midnight-straddle: {len(events)} sessions, expected 1")
            if events:
                check(
                    (events[0]["a_time"], events[0]["b_time"])
                    == ("2026-05-01T23:40:00", "2026-05-01T23:50:00"),
                    f"midnight-straddle: representative pair {events[0]}",
                )
        elif scenario == "two-meetings-one-day":
            events = got["co_presence"]["evidence"]["events"]
            check(len(events) == 2,
                  f"two-meetings-one-day: {len(events)} sessions, expected 2")
            check([event["a_time"][11:16] for event in events] == ["09:00", "18:00"],
                  f"two-meetings-one-day: representative times {events}")

        print(f"{scenario:<24} verified ({len(ds.rows)} rows)")
        conn.close()

    if failures:
        print("HARDENING FAILURES:")
        for failure in failures:
            print(" -", failure)
        sys.exit(1)


def verify(ds: Dataset, pairs, expect, expect_mode,
           caveat_pairs=frozenset(), shared_area=None):
    conn = _connection(ds)

    n_users = conn.execute(
        "SELECT COUNT(DISTINCT phone_number) n FROM cdr_records").fetchone()["n"]
    failures, summary = [], []
    mode_line = None
    for scen, (pa, pb) in pairs.items():
        result = _compute(conn, scen, pa, pb)
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

    conn.close()

    print(f"\n== {ds.name}: {len(ds.rows)} rows, {n_users} subscribers, "
          f"mode {mode_line} ==")
    for s in summary:
        print(s)
    if failures:
        print("FAILURES:")
        for f in failures:
            print(" -", f)
        sys.exit(1)


def write_xlsx(ds: Dataset, path: str | pathlib.Path):
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
    print("\n== isolated method-hardening scenarios ==")
    verify_hardening_scenarios()
    write_xlsx(strangers, STRANGERS_OUTPUT)
    write_xlsx(closeknit, CLOSEKNIT_OUTPUT)
    print("OK")
