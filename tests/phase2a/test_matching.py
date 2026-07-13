"""Contact matcher: pure gate engine, fact-gathering SQL, routes, and the
click-to-save export staging (spec 2026-07-12-contact-matcher-design.md).

The gate engine is exercised twice: pure unit tests with fabricated facts (every
tier combination without needing 50-record fixtures), and an end-to-end fixture
dataset whose expected findings are worked out by hand below.
"""

import io

import pandas as pd
import pytest
from openpyxl import load_workbook

from app import create_app
from app.matching import gates

COLUMNS = ["phone_number", "imei", "area", "timestamp", "call_type",
           "duration_seconds", "other_party", "other_imei", "other_area"]

# Pair under test: A=100, B=200. Background subscribers 300-700 (other_users=5;
# COMMON_USER_FRACTION=0.20 alone would make the common threshold >=1 other user,
# but the COMMON_MIN_USERS=3 floor raises it to >=3 in a population this small).
#
# Expected facts, worked by hand:
#   direct:   4 rows (2 A-out, 2 B-out) -> both directions, 2 calls + 2 SMS,
#             volume 4 -> Medium (DIRECT_MEDIUM=3).
#   contacts: A={P1,P2,P9,PA}, B={P1,P2,P9,PB}; shared={P1,P2,P9};
#             P9 has 2 other users -- under the floor of 3, so DISTINCTIVE here
#             (the floor protecting a tiny population); P1/P2 distinctive too.
#   co-presence: Cafe 01-03 (two pairings, one day -> ONE event, distinctive),
#             Edge 01-06 (exactly 3600s apart -> inclusive window counts),
#             Downtown 01-05 (300+400 have rows there -- 2 others, under the
#             floor of 3, so distinctive in this tiny population),
#             Far 01-07 (3660s apart -> NOT an event). Total 3 events.
#   samples:  n_a=11, n_b=10 -> sample gate Low (N_MEDIUM=15) binds both
#             indirect findings; direct is volume-rated and stays Medium.
ROWS = [
    # direct A<->B
    ("100", "iA", "Home", "2026-01-01T09:00:00", 1, 60, "200", "", ""),
    ("100", "iA", "Home", "2026-01-02T09:00:00", 11, 0, "200", "", ""),
    ("200", "iB", "Bwork", "2026-01-02T10:00:00", 1, 60, "100", "", ""),
    ("200", "iB", "Bwork", "2026-01-04T10:00:00", 11, 0, "100", "", ""),
    # shared distinctive contacts P1, P2
    ("100", "iA", "Home", "2026-01-01T10:00:00", 1, 60, "P1", "", ""),
    ("100", "iA", "Home", "2026-01-02T10:30:00", 1, 60, "P2", "", ""),
    ("200", "iB", "Bwork", "2026-01-03T10:00:00", 1, 60, "P1", "", ""),
    ("200", "iB", "Bwork", "2026-01-03T11:00:00", 1, 60, "P2", "", ""),
    # shared COMMON contact P9 (background users have it too)
    ("100", "iA", "Home", "2026-01-04T09:00:00", 1, 60, "P9", "", ""),
    ("200", "iB", "Bwork", "2026-01-04T11:00:00", 1, 60, "P9", "", ""),
    ("300", "i3", "Elsewhere", "2026-01-01T09:00:00", 1, 60, "P9", "", ""),
    ("400", "i4", "Elsewhere", "2026-01-01T10:00:00", 1, 60, "P9", "", ""),
    # one-sided contacts
    ("100", "iA", "Home", "2026-01-05T09:00:00", 1, 60, "PA", "", ""),
    ("200", "iB", "Bwork", "2026-01-05T09:00:00", 1, 60, "PB", "", ""),
    # co-presence: Cafe (distinctive, two pairings same day -> one event)
    ("100", "iA", "Cafe", "2026-01-03T10:00:00", 1, 30, "", "", ""),
    ("200", "iB", "Cafe", "2026-01-03T10:30:00", 1, 30, "", "", ""),
    ("100", "iA", "Cafe", "2026-01-03T11:00:00", 1, 30, "", "", ""),
    # co-presence boundary: Edge exactly 60 min apart (inclusive -> event)
    ("100", "iA", "Edge", "2026-01-06T12:00:00", 1, 30, "", "", ""),
    ("200", "iB", "Edge", "2026-01-06T13:00:00", 1, 30, "", "", ""),
    # NOT co-presence: Far 61 min apart
    ("100", "iA", "Far", "2026-01-07T14:00:00", 1, 30, "", "", ""),
    ("200", "iB", "Far", "2026-01-07T15:01:00", 1, 30, "", "", ""),
    # co-presence in a COMMON area: Downtown (background users go there too)
    ("100", "iA", "Downtown", "2026-01-05T09:00:00", 1, 30, "", "", ""),
    ("200", "iB", "Downtown", "2026-01-05T09:20:00", 1, 30, "", "", ""),
    ("300", "i3", "Downtown", "2026-01-02T09:00:00", 1, 30, "", "", ""),
    ("400", "i4", "Downtown", "2026-01-02T10:00:00", 1, 30, "", "", ""),
    # background population filler (makes other_users = 5)
    ("500", "i5", "Elsewhere", "2026-01-01T11:00:00", 1, 30, "", "", ""),
    ("600", "i6", "Elsewhere", "2026-01-01T12:00:00", 1, 30, "", "", ""),
    ("700", "i7", "Elsewhere", "2026-01-01T13:00:00", 1, 30, "", "", ""),
]


@pytest.fixture()
def client(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    c = app.test_client()
    c.post("/api/setup", json={"username": "nadim", "password": "hunter2"})
    return c


@pytest.fixture()
def dataset_id(client, tmp_path):
    df = pd.DataFrame(ROWS, columns=COLUMNS)
    path = tmp_path / "pair.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with open(path, "rb") as fh:
        data = {"name": "pair", "file": (io.BytesIO(fh.read()), "pair.xlsx")}
    res = client.post("/api/imports", data=data, content_type="multipart/form-data")
    return res.get_json()["data"]["dataset_id"]


def _mk_target(client, dataset_id, name, phone):
    return client.post("/api/targets", json={
        "name": name, "dataset_id": dataset_id, "phone_number": phone,
    }).get_json()["data"]["id"]


@pytest.fixture()
def pair(client, dataset_id):
    """(target_a_id, target_b_id) for subscribers 100 and 200."""
    return (_mk_target(client, dataset_id, "A", "100"),
            _mk_target(client, dataset_id, "B", "200"))


def _match(client, a, b):
    return client.post("/api/match", json={"target_a_id": a, "target_b_id": b})


# ---- pure gate engine ----

def _facts(**over):
    """A baseline facts dict that produces ALL THREE findings at High, so each
    test overrides exactly the knob it is about."""
    base = {
        "name_a": "A", "name_b": "B",
        "n_a": 60, "n_b": 60,
        "span_a": ("2026-01-01T00:00:00", "2026-01-30T00:00:00"),
        "span_b": ("2026-01-01T00:00:00", "2026-01-30T00:00:00"),
        "contacts_a": {"P1": 5, "P2": 4, "P3": 3},
        "contacts_b": {"P1": 6, "P2": 2, "P3": 1},
        "areas_a": {"X", "Y"}, "areas_b": {"X", "Z"},
        "direct": {"total": 12, "calls": 10, "sms": 2, "a_to_b": 6, "b_to_a": 6,
                   "first": "2026-01-01T09:00:00", "last": "2026-01-28T09:00:00"},
        "co_events": [{"area": "X", "day": f"2026-01-{d:02d}",
                       "a_time": None, "b_time": None} for d in range(10, 15)],
        "other_users": 10,
        "contact_commonality": {"P1": 0, "P2": 0, "P3": 0},
        "area_commonality": {"X": 0},
    }
    base.update(over)
    return base


def _by_type(result):
    return {f["type"]: f for f in result["findings"]}


def test_baseline_facts_yield_all_three_findings_high():
    result = gates.build_findings(_facts())
    f = _by_type(result)
    assert set(f) == {"direct_contact", "mutual_contacts", "co_presence"}
    assert all(x["strength"] == "High" for x in f.values())
    assert result["no_link"] is False


def test_direct_volume_tiers():
    assert _by_type(gates.build_findings(_facts()))["direct_contact"]["strength"] == "High"
    med = _facts(direct={"total": 3, "calls": 3, "sms": 0, "a_to_b": 3, "b_to_a": 0,
                         "first": None, "last": None})
    assert _by_type(gates.build_findings(med))["direct_contact"]["strength"] == "Medium"
    low = _facts(direct={"total": 1, "calls": 1, "sms": 0, "a_to_b": 0, "b_to_a": 1,
                         "first": None, "last": None})
    assert _by_type(gates.build_findings(low))["direct_contact"]["strength"] == "Low"


def test_direct_contact_is_not_dragged_down_by_indirect_gates():
    """The caveat-1 absurdity guard: two people who call each other constantly
    but share nothing else must NOT come out Low."""
    result = gates.build_findings(_facts(
        contacts_a={}, contacts_b={}, co_events=[], area_commonality={},
        n_a=6, n_b=6,  # sample gate would be Low -- must not touch direct
    ))
    f = _by_type(result)
    assert set(f) == {"direct_contact"}
    assert f["direct_contact"]["strength"] == "High"


def test_sample_gate_binds_indirect_findings():
    result = gates.build_findings(_facts(n_a=10))  # min(N) below N_MEDIUM
    f = _by_type(result)
    assert f["mutual_contacts"]["strength"] == "Low"
    assert "sample" in f["mutual_contacts"]["bound_by"]
    assert f["co_presence"]["strength"] == "Low"
    assert "sample" in f["co_presence"]["bound_by"]


def test_window_overlap_gate_binds():
    # B observed for 30 days but only the last 3 overlap A -> ratio 3/30 = 0.1.
    result = gates.build_findings(_facts(
        span_b=("2026-01-28T00:00:00", "2026-02-26T00:00:00")))
    f = _by_type(result)
    assert f["mutual_contacts"]["strength"] == "Low"
    assert f["mutual_contacts"]["bound_by"] == ["window overlap"]
    assert any("overlap only" in c for c in result["caveats"])


def test_distinctiveness_gate_discounts_common_contacts():
    # All three shared contacts are common (>= 20% of the 10 other users have
    # them) -> the mutual finding doesn't even fire (fewer than 2 distinctive).
    result = gates.build_findings(_facts(
        contact_commonality={"P1": 5, "P2": 4, "P3": 9}))
    assert "mutual_contacts" not in _by_type(result)


def test_distinctiveness_gate_binds_when_mixed():
    # P1/P2 distinctive, P3 common -> fires, but distinctive share 2/3 = 0.67 High;
    # make it bind by dropping to exactly 1 common of 3... instead rate Medium via
    # 2 distinct / 4 shared. Add P4 shared+common: 2/4 = 0.5 -> Medium binds.
    facts = _facts(
        contacts_a={"P1": 5, "P2": 4, "P3": 3, "P4": 2},
        contacts_b={"P1": 6, "P2": 2, "P3": 1, "P4": 1},
        contact_commonality={"P1": 0, "P2": 0, "P3": 9, "P4": 8})
    f = _by_type(gates.build_findings(facts))
    assert f["mutual_contacts"]["strength"] == "Medium"
    assert f["mutual_contacts"]["bound_by"] == ["distinctiveness"]


def test_event_count_gate_binds():
    result = gates.build_findings(_facts(co_events=[
        {"area": "X", "day": "2026-01-10", "a_time": None, "b_time": None},
        {"area": "X", "day": "2026-01-11", "a_time": None, "b_time": None},
    ]))
    f = _by_type(result)
    assert f["co_presence"]["strength"] == "Medium"
    assert f["co_presence"]["bound_by"] == ["event count"]


def test_busy_tower_discount_binds_location_distinctiveness():
    result = gates.build_findings(_facts(area_commonality={"X": 9}))
    f = _by_type(result)
    assert f["co_presence"]["strength"] == "Low"
    assert f["co_presence"]["bound_by"] == ["location distinctiveness"]


def test_no_link_when_nothing_overlaps():
    result = gates.build_findings(_facts(
        contacts_a={"PA": 1}, contacts_b={"PB": 1},
        direct={"total": 0, "calls": 0, "sms": 0, "a_to_b": 0, "b_to_a": 0,
                "first": None, "last": None},
        co_events=[], contact_commonality={}, area_commonality={}))
    assert result["findings"] == []
    assert result["no_link"] is True


def test_zero_record_target_is_a_caveat_not_a_crash():
    result = gates.build_findings(_facts(n_b=0, span_b=None))
    assert result["no_link"] is True
    assert any("B has no records" in c for c in result["caveats"])


def test_shared_areas_without_time_overlap_are_a_detail_not_a_finding():
    result = gates.build_findings(_facts())
    # X is a co-presence area; Y/Z are one-sided; nothing shared-without-time.
    assert result["details"]["shared_areas_no_time_overlap"] == []
    result = gates.build_findings(_facts(areas_a={"X", "Q"}, areas_b={"X", "Q"}))
    assert result["details"]["shared_areas_no_time_overlap"] == ["Q"]
    assert "Q" not in {e["area"] for e in _facts()["co_events"]}


def test_window_overlap_ratio_maths():
    day = "T00:00:00"
    # identical spans
    assert gates.window_overlap_ratio(
        ("2026-01-01" + day, "2026-01-10" + day),
        ("2026-01-01" + day, "2026-01-10" + day)) == 1.0
    # disjoint
    assert gates.window_overlap_ratio(
        ("2026-01-01" + day, "2026-01-10" + day),
        ("2026-02-01" + day, "2026-02-10" + day)) == 0.0
    # 5 of the shorter span's 10 days overlap
    assert gates.window_overlap_ratio(
        ("2026-01-01" + day, "2026-01-10" + day),
        ("2026-01-06" + day, "2026-01-20" + day)) == 0.5
    # single-day spans are 1 day, not 0
    assert gates.window_overlap_ratio(
        ("2026-01-01" + day, "2026-01-01" + day),
        ("2026-01-01" + day, "2026-01-01" + day)) == 1.0


def test_weakest_reports_every_gate_at_the_minimum():
    strength, bound = gates.weakest(
        {"a": "High", "b": "Low", "c": "Medium", "d": "Low"})
    assert strength == "Low"
    assert bound == ["b", "d"]


# ---- adaptive gates: dataset mode, commonality floor, cliff disclosure ----
# (spec 2026-07-13-adaptive-matcher-gates.md)

def test_commonality_floor_protects_tiny_populations():
    """One other subscriber must never brand a contact common (0.2 * 3 = 0.6
    would, without the COMMON_MIN_USERS floor)."""
    facts = _facts(other_users=3, contact_commonality={"P1": 1, "P2": 1, "P3": 1})
    f = _by_type(gates.build_findings(facts))["mutual_contacts"]
    assert all(c["distinctive"] for c in f["evidence"]["shared_contacts"])


def test_commonality_floor_still_discounts_at_scale():
    # 3 others sharing it clears the floor even where 20% alone would need only 1.
    facts = _facts(other_users=5, contact_commonality={"P1": 3, "P2": 3, "P3": 3})
    assert "mutual_contacts" not in _by_type(gates.build_findings(facts))


def test_small_population_caveat():
    r = gates.build_findings(_facts(other_users=5))
    assert any("too few" in c for c in r["caveats"])
    r = gates.build_findings(_facts(other_users=10))
    assert not any("too few" in c for c in r["caveats"])


def test_dataset_mode_classification_tiers():
    for density, mode, cls in [
        (0.4, "strangers", "High"),      # margin 2.0/0.4 = 5.0
        (1.2, "strangers", "Medium"),    # margin 1.67
        (1.6, "strangers", "Low"),       # margin 1.25
        (1.9, "strangers", "Near tie"),  # margin 1.05
        (2.1, "close-knit", "Near tie"), # margin 1.05, other side of the line
        (2.4, "close-knit", "Low"),      # margin 1.2
        (3.0, "close-knit", "Medium"),   # margin 1.5
        (5.0, "close-knit", "High"),     # margin 2.5
        (0.0, "strangers", "High"),      # empty/atomized dataset: decisively strangers
    ]:
        ctx = gates.classify_dataset(density)
        assert (ctx["mode"], ctx["classification"]) == (mode, cls), density
        assert ctx["boundary"] == gates.CLOSE_KNIT_BOUNDARY


def test_payload_carries_dataset_context():
    r = gates.build_findings(_facts(dataset_density=0.4))
    assert r["dataset_context"]["mode"] == "strangers"
    r = gates.build_findings(_facts(dataset_density=4.0, contact_spread_median=6))
    assert r["dataset_context"]["mode"] == "close-knit"
    # the zero-record early return still describes the dataset
    r = gates.build_findings(_facts(n_b=0, span_b=None))
    assert "dataset_context" in r


def _ck_facts(**over):
    """Close-knit variant of the baseline: dense dataset, typical contact shared
    by 6 subscribers."""
    return _facts(dataset_density=4.0, contact_spread_median=6, **over)


def test_close_knit_group_wide_overlap_rates_medium_never_suppressed():
    """In a clique, sharing only the group's common fabric is still a REAL mutual
    relationship: solid overlap, nothing pair-specific -> Medium bound by
    distinctiveness, never 'no link'."""
    facts = _ck_facts(contact_commonality={"P1": 6, "P2": 8, "P3": 7})
    f = _by_type(gates.build_findings(facts))["mutual_contacts"]
    assert f["strength"] == "Medium"
    assert f["bound_by"] == ["distinctiveness"]


def test_close_knit_rare_shared_contacts_rate_high():
    # All shared contacts rarer than the dataset-typical shared spread of 6:
    # pair-specific mutuals beyond the group fabric.
    facts = _ck_facts(contact_commonality={"P1": 1, "P2": 0, "P3": 2})
    f = _by_type(gates.build_findings(facts))["mutual_contacts"]
    assert f["strength"] == "High"


def test_close_knit_single_shared_contact_fires():
    # The >=2-distinctive suppression floor is strangers-mode only. One shared
    # group-wide contact is trivial overlap -> Low, but it FIRES.
    facts = _ck_facts(contacts_a={"P1": 5}, contacts_b={"P1": 2},
                      contact_commonality={"P1": 6})
    f = _by_type(gates.build_findings(facts))["mutual_contacts"]
    assert f["strength"] == "Low"


def test_close_knit_one_rare_contact_rates_medium_with_a_near_note():
    # 1 rare shared contact: one short of the High count -- rate Medium and SAY
    # it was close (cliff disclosure).
    facts = _ck_facts(contact_commonality={"P1": 1, "P2": 8, "P3": 7})
    f = _by_type(gates.build_findings(facts))["mutual_contacts"]
    assert f["strength"] == "Medium"
    assert any("rare shared contacts is just short of High: 1 vs 2" in n
               for n in f["notes"])


def test_strangers_mode_still_suppresses_all_common_shared():
    # Same commonality profile as the close-knit Low case, but a sparse dataset:
    # the old rule (fires only from 2 distinctive) still applies.
    facts = _facts(dataset_density=0.3,
                   contact_commonality={"P1": 6, "P2": 8, "P3": 7})
    assert "mutual_contacts" not in _by_type(gates.build_findings(facts))


def test_near_boundary_notes_flag_cliff_cases():
    r = _by_type(gates.build_findings(_facts(n_a=49)))
    assert any("just short of High" in n and "49" in n
               for n in r["mutual_contacts"]["notes"])
    direct_2 = _facts(direct={"total": 2, "calls": 2, "sms": 0, "a_to_b": 2,
                              "b_to_a": 0, "first": None, "last": None})
    f = _by_type(gates.build_findings(direct_2))["direct_contact"]
    assert any("just short of Medium" in n for n in f["notes"])
    events_4 = _facts(co_events=[
        {"area": "X", "day": f"2026-01-{d:02d}", "a_time": None, "b_time": None}
        for d in range(10, 14)])
    f = _by_type(gates.build_findings(events_4))["co_presence"]
    assert any("event count" in n and "just short of High" in n for n in f["notes"])


def test_no_notes_when_far_from_every_line():
    f = _by_type(gates.build_findings(_facts()))["mutual_contacts"]
    # n=60, share 1.0, distinctiveness 1.0, window 1.0: nothing near a boundary.
    assert f["notes"] == []


# ---- end-to-end: the fixture dataset through the API ----

def test_match_requires_auth(app_data_dir, bootstrap_key):
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    res = app.test_client().post("/api/match", json={"target_a_id": 1, "target_b_id": 2})
    assert res.status_code == 401


def test_match_validation(client, pair):
    a, b = pair
    assert _match(client, a, a).status_code == 400          # same target twice
    assert _match(client, a, 9999).status_code == 404       # unknown target
    res = client.post("/api/match", json={"target_a_id": "x", "target_b_id": b})
    assert res.status_code == 400                            # non-int id


def test_match_rejects_cross_dataset(client, dataset_id, pair, tmp_path):
    df = pd.DataFrame(ROWS[:1], columns=COLUMNS)
    path = tmp_path / "other.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with open(path, "rb") as fh:
        data = {"name": "other", "file": (io.BytesIO(fh.read()), "other.xlsx")}
    ds2 = client.post("/api/imports", data=data,
                      content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    foreign = _mk_target(client, ds2, "F", "100")
    res = _match(client, pair[0], foreign)
    assert res.status_code == 400
    assert "same dataset" in res.get_json()["error"]["message"]


def test_match_fixture_findings(client, pair):
    a, b = pair
    data = _match(client, a, b).get_json()["data"]
    f = {x["type"]: x for x in data["findings"]}
    assert set(f) == {"direct_contact", "mutual_contacts", "co_presence"}

    direct = f["direct_contact"]
    assert direct["strength"] == "Medium"          # 4 interactions
    assert direct["evidence"]["total"] == 4
    assert direct["evidence"]["calls"] == 2 and direct["evidence"]["sms"] == 2
    assert direct["evidence"]["a_to_b"] == 2 and direct["evidence"]["b_to_a"] == 2
    assert "both directions" in direct["headline"]

    mutual = f["mutual_contacts"]
    shared = {c["party"]: c for c in mutual["evidence"]["shared_contacts"]}
    assert set(shared) == {"P1", "P2", "P9"}
    assert shared["P1"]["distinctive"] and shared["P2"]["distinctive"]
    # P9 is contacted by 2 others -- 20% alone would call that common, but the
    # COMMON_MIN_USERS floor (3) protects evidence in a 5-other-user population.
    assert shared["P9"]["distinctive"]
    assert shared["P9"]["other_users_with"] == 2
    # n=11 records on the weaker side -> the sample gate binds the min()
    assert mutual["strength"] == "Low"
    assert "sample" in mutual["bound_by"]

    co = f["co_presence"]
    events = {(e["area"], e["day"]) for e in co["evidence"]["events"]}
    assert events == {("Cafe", "2026-01-03"),      # deduped: 2 pairings, 1 event
                      ("Edge", "2026-01-06"),      # exactly 60 min -> inclusive
                      ("Downtown", "2026-01-05")}  # common area still an EVENT
    assert co["evidence"]["gates"]["event count"] == "Medium"       # 3 events
    assert co["evidence"]["gates"]["location distinctiveness"] == "High"  # 3/3 (floor)
    assert co["strength"] == "Low"
    assert "sample" in co["bound_by"]

    # Far (61 min apart) must not appear anywhere
    assert "Far" not in {e["area"] for e in co["evidence"]["events"]}
    # Far IS a shared area without time overlap -> detail row
    assert data["details"]["shared_areas_no_time_overlap"] == ["Far"]

    # 7 subscribers with almost no contact overlap: decisively strangers mode,
    # and the 5-other-subscriber population triggers the small-population caveat.
    assert data["dataset_context"]["mode"] == "strangers"
    assert any("too few" in c for c in data["caveats"])


def test_match_is_byte_symmetric_across_midnight(client, dataset_id, tmp_path):
    """A-vs-B and B-vs-A must be identical. Midnight-straddling meet-ups used to
    dedupe differently depending on whose calendar day keyed the event."""
    rows = [
        ("100", "iA", "M", "2026-01-01T23:50:00", 1, 30, "", "", ""),
        ("100", "iA", "M", "2026-01-02T00:30:00", 1, 30, "", "", ""),
        ("200", "iB", "M", "2026-01-02T00:20:00", 1, 30, "", "", ""),
        ("200", "iB", "M", "2026-01-02T00:40:00", 1, 30, "", "", ""),
    ]
    df = pd.DataFrame(rows, columns=COLUMNS)
    path = tmp_path / "midnight.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with open(path, "rb") as fh:
        data = {"name": "midnight", "file": (io.BytesIO(fh.read()), "midnight.xlsx")}
    ds = client.post("/api/imports", data=data,
                     content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    a = _mk_target(client, ds, "A", "100")
    b = _mk_target(client, ds, "B", "200")
    ab = _match(client, a, b).get_json()["data"]
    ba = _match(client, b, a).get_json()["data"]
    ab.pop("computed_at"), ba.pop("computed_at")
    assert ab == ba


def test_match_is_symmetric(client, pair):
    a, b = pair
    ab = _match(client, a, b).get_json()["data"]
    ba = _match(client, b, a).get_json()["data"]
    assert ({f["type"]: f["strength"] for f in ab["findings"]}
            == {f["type"]: f["strength"] for f in ba["findings"]})


def test_match_run_stores_nothing(client, pair):
    _match(client, *pair)
    assert client.get("/api/match/saved").get_json()["data"] == []


# ---- click-to-save staging ----

def test_save_match_recomputes_and_replaces_on_same_pair(client, pair):
    a, b = pair
    assert client.post("/api/match/save",
                       json={"target_a_id": a, "target_b_id": b}).status_code == 200
    # Saving again -- even with the pair REVERSED -- replaces, never duplicates.
    assert client.post("/api/match/save",
                       json={"target_a_id": b, "target_b_id": a}).status_code == 200
    saved = client.get("/api/match/saved").get_json()["data"]
    assert len(saved) == 1
    assert {f["type"] for f in saved[0]["result"]["findings"]} == \
        {"direct_contact", "mutual_contacts", "co_presence"}


def test_delete_saved_match(client, pair):
    a, b = pair
    client.post("/api/match/save", json={"target_a_id": a, "target_b_id": b})
    saved_id = client.get("/api/match/saved").get_json()["data"][0]["id"]
    assert client.delete(f"/api/match/saved/{saved_id}").status_code == 200
    assert client.get("/api/match/saved").get_json()["data"] == []
    assert client.delete(f"/api/match/saved/{saved_id}").status_code == 404


def test_save_and_delete_write_audit_rows(client, pair, bootstrap_key):
    a, b = pair
    client.post("/api/match/save", json={"target_a_id": a, "target_b_id": b})
    saved_id = client.get("/api/match/saved").get_json()["data"][0]["id"]
    client.delete(f"/api/match/saved/{saved_id}")
    from app.infra import storage
    conn = storage.connect(bootstrap_key)
    events = [r["event_type"] for r in conn.execute(
        "SELECT event_type FROM audit_log WHERE event_type LIKE 'PAIR_MATCH_%' "
        "ORDER BY id").fetchall()]
    conn.close()
    assert events == ["PAIR_MATCH_SAVE", "PAIR_MATCH_DELETE"]


def test_deleting_a_target_cascades_its_saved_matches(client, pair):
    a, b = pair
    client.post("/api/match/save", json={"target_a_id": a, "target_b_id": b})
    assert client.delete(f"/api/targets/{a}").status_code == 200
    assert client.get("/api/match/saved").get_json()["data"] == []


# ---- saved tallies ----

def test_save_tally_recomputes_server_side(client, pair):
    a, _ = pair
    live = client.get(f"/api/targets/{a}/frequency?rank_by=area").get_json()["data"]
    saved = client.post("/api/frequency/save", json={
        "target_id": a, "rank_by": "area"}).get_json()["data"]
    assert saved["top"] == live["top"]
    assert saved["total_records"] == live["total_records"]
    listed = client.get("/api/frequency/saved").get_json()["data"]
    assert len(listed) == 1
    assert listed[0]["tally"]["top"] == live["top"]
    assert "Location / tower ranking" in listed[0]["filter_label"]


def test_save_tally_validates_filters(client, pair):
    a, _ = pair
    assert client.post("/api/frequency/save", json={
        "target_id": a, "rank_by": "nope"}).status_code == 400
    assert client.post("/api/frequency/save", json={
        "target_id": 9999, "rank_by": "area"}).status_code == 404
    assert client.post("/api/frequency/save", json={
        "target_id": a, "rank_by": "area", "hour_from": "99"}).status_code == 400


def test_saved_tallies_accumulate_and_delete(client, pair):
    a, _ = pair
    client.post("/api/frequency/save", json={"target_id": a, "rank_by": "area"})
    client.post("/api/frequency/save", json={"target_id": a, "rank_by": "other_party"})
    listed = client.get("/api/frequency/saved").get_json()["data"]
    assert len(listed) == 2                       # tallies accumulate (unlike pairs)
    assert client.delete(f"/api/frequency/saved/{listed[0]['id']}").status_code == 200
    assert len(client.get("/api/frequency/saved").get_json()["data"]) == 1
    assert client.delete(f"/api/frequency/saved/{listed[0]['id']}").status_code == 404


# ---- pair record ledger (spec 2026-07-13-pair-record-ledger-design.md) ----
# The RECORDS themselves, not a verdict about them: no strengths, no confidence.

def _ledger(client, a, b):
    return client.post("/api/ledger", json={"target_a_id": a, "target_b_id": b})


def test_ledger_lists_every_record_in_four_categories(client, pair):
    a, b = pair
    data = _ledger(client, a, b).get_json()["data"]
    rows = data["rows"]
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    assert set(by_cat) == {"direct", "shared_contact", "meet_up_location",
                           "shared_location"}
    # direct: the 4 A<->B records, BOTH sides' rows
    assert len(by_cat["direct"]) == 4
    assert {r["who_phone"] for r in by_cat["direct"]} == {"100", "200"}
    # shared contacts P1/P2/P9: one record per side per contact = 6 rows
    assert len(by_cat["shared_contact"]) == 6
    assert {r["other_party"] for r in by_cat["shared_contact"]} == {"P1", "P2", "P9"}
    # shared_location: the Far records (shared area, no time overlap) -- one each
    assert {r["area"] for r in by_cat["shared_location"]} == {"Far"}
    assert len(by_cat["shared_location"]) == 2
    # meet-up areas: Cafe / Edge / Downtown
    assert {r["area"] for r in by_cat["meet_up_location"]} == {"Cafe", "Edge", "Downtown"}
    assert data["row_count"] == len(rows)
    assert data["category_counts"]["direct"] == 4


def test_ledger_assigns_overlapping_records_to_one_category(client, tmp_path):
    """A shared-contact record in a meet-up area is still one source CDR."""
    rows = [
        ("100", "iA", "Cafe", "2026-01-01T10:00:00", 1, 60, "200", "", ""),
        ("200", "iB", "Cafe", "2026-01-01T10:10:00", 2, 60, "100", "", ""),
        ("100", "iA", "Cafe", "2026-01-01T11:00:00", 1, 60, "X", "", ""),
        ("200", "iB", "Cafe", "2026-01-01T11:30:00", 1, 60, "X", "", ""),
    ]
    df = pd.DataFrame(rows, columns=COLUMNS)
    path = tmp_path / "overlapping_ledger.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with open(path, "rb") as fh:
        data = {"name": "overlap", "file": (io.BytesIO(fh.read()), path.name)}
    ds = client.post("/api/imports", data=data,
                     content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    a = _mk_target(client, ds, "A", "100")
    b = _mk_target(client, ds, "B", "200")

    ledger_rows = _ledger(client, a, b).get_json()["data"]["rows"]
    assert len(ledger_rows) == len(rows)
    assert [r["category"] for r in ledger_rows] == [
        "direct", "direct", "shared_contact", "shared_contact"]
    assert len({r["timestamp"] for r in ledger_rows}) == len(rows)


def test_ledger_rows_carry_the_actual_record_detail(client, pair):
    a, b = pair
    rows = _ledger(client, a, b).get_json()["data"]["rows"]
    direct = [r for r in rows if r["category"] == "direct"]
    first = min(direct, key=lambda r: r["timestamp"])
    assert first["timestamp"] == "2026-01-01T09:00:00"   # date AND time
    assert first["call_type"] == 1
    assert first["duration_seconds"] == 60
    assert first["area"] == "Home"
    # nothing in a ledger row is a verdict
    assert "strength" not in first and "confidence" not in first


def test_ledger_names_both_parties_on_a_direct_row(client, pair):
    """We know who both sides are -- name them, don't print bare numbers."""
    a, b = pair
    rows = _ledger(client, a, b).get_json()["data"]["rows"]
    direct = [r for r in rows if r["category"] == "direct"]
    a_rows = [r for r in direct if r["who_phone"] == "100"]
    assert a_rows and all(r["who"] == "A" for r in a_rows)
    assert all(r["other_party_name"] == "B" for r in a_rows)
    assert all(r["other_party_is_target"] for r in direct)


def test_ledger_flags_a_shared_contact_who_is_also_a_target(client, tmp_path):
    """A mutual contact who is themselves under investigation must be flagged and
    NAMED, not left as a bare number. (A target must be a subscriber, so this
    needs a dataset where the shared contact has records of their own.)"""
    rows = [
        # A and B both call subscriber C -- a shared contact who is also a target
        ("100", "iA", "Home", "2026-01-01T09:00:00", 1, 60, "300", "", ""),
        ("200", "iB", "Bwork", "2026-01-02T09:00:00", 1, 60, "300", "", ""),
        # ... and both call P2, an outsider
        ("100", "iA", "Home", "2026-01-03T09:00:00", 1, 60, "P2", "", ""),
        ("200", "iB", "Bwork", "2026-01-04T09:00:00", 1, 60, "P2", "", ""),
        # C's own records make them a subscriber (and thus targetable)
        ("300", "iC", "Cplace", "2026-01-05T09:00:00", 1, 60, "999", "", ""),
        ("400", "i4", "Elsewhere", "2026-01-05T10:00:00", 1, 60, "888", "", ""),
    ]
    df = pd.DataFrame(rows, columns=COLUMNS)
    path = tmp_path / "shared_target.xlsx"
    df.to_excel(path, index=False, engine="openpyxl")
    with open(path, "rb") as fh:
        data = {"name": "st", "file": (io.BytesIO(fh.read()), "shared_target.xlsx")}
    ds = client.post("/api/imports", data=data,
                     content_type="multipart/form-data").get_json()["data"]["dataset_id"]
    a = _mk_target(client, ds, "A", "100")
    b = _mk_target(client, ds, "B", "200")
    _mk_target(client, ds, "Carlos", "300")

    ledger_rows = _ledger(client, a, b).get_json()["data"]["rows"]
    c_rows = [r for r in ledger_rows if r["other_party"] == "300"]
    assert len(c_rows) == 2                                  # one from each side
    assert all(r["other_party_is_target"] for r in c_rows)
    assert all(r["other_party_name"] == "Carlos" for r in c_rows)
    # the outsider is not flagged and carries no name
    p2 = next(r for r in ledger_rows if r["other_party"] == "P2")
    assert p2["other_party_is_target"] is False
    assert p2["other_party_name"] is None


def test_ledger_lists_common_items_but_labels_them(client, pair):
    """Common contacts/areas are NOT evidence, but they are not hidden either --
    an analyst must be able to audit what the matcher discounted."""
    a, b = pair
    rows = _ledger(client, a, b).get_json()["data"]["rows"]
    shared = {r["other_party"]: r for r in rows if r["category"] == "shared_contact"}
    # in this 5-other-user fixture the floor keeps every shared contact distinctive
    assert all(shared[p]["distinctive"] is True for p in ("P1", "P2", "P9"))
    downtown = [r for r in rows if r["area"] == "Downtown"]
    assert downtown and all(r["distinctive"] is True for r in downtown)


def test_ledger_is_symmetric(client, pair):
    a, b = pair
    ab = _ledger(client, a, b).get_json()["data"]
    ba = _ledger(client, b, a).get_json()["data"]
    ab.pop("computed_at"), ba.pop("computed_at")
    assert ab == ba


def test_ledger_run_stores_nothing(client, pair):
    _ledger(client, *pair)
    assert client.get("/api/ledger/saved").get_json()["data"] == []


def test_save_ledger_accumulates_and_deletes(client, pair):
    """Unlike pair matches (which replace), ledgers accumulate: saving the same
    pair twice is a legitimate act."""
    a, b = pair
    first = client.post("/api/ledger/save", json={"target_a_id": a, "target_b_id": b})
    assert first.status_code == 200
    assert first.get_json()["data"]["row_count"] > 0
    client.post("/api/ledger/save", json={"target_a_id": b, "target_b_id": a})
    saved = client.get("/api/ledger/saved").get_json()["data"]
    assert len(saved) == 2
    assert saved[0]["pair"]["target_a"]["name"] == "A"
    assert saved[0]["row_count"] == first.get_json()["data"]["row_count"]
    assert client.delete(f"/api/ledger/saved/{saved[0]['id']}").status_code == 200
    assert len(client.get("/api/ledger/saved").get_json()["data"]) == 1
    assert client.delete(f"/api/ledger/saved/{saved[0]['id']}").status_code == 404


def test_save_ledger_writes_audit_rows(client, pair, bootstrap_key):
    a, b = pair
    client.post("/api/ledger/save", json={"target_a_id": a, "target_b_id": b})
    saved_id = client.get("/api/ledger/saved").get_json()["data"][0]["id"]
    client.delete(f"/api/ledger/saved/{saved_id}")
    from app.infra import storage
    conn = storage.connect(bootstrap_key)
    events = [r["event_type"] for r in conn.execute(
        "SELECT event_type FROM audit_log WHERE event_type LIKE 'LEDGER_%' "
        "ORDER BY id").fetchall()]
    conn.close()
    assert events == ["LEDGER_SAVE", "LEDGER_DELETE"]


def test_ledger_validation_and_auth(client, pair, app_data_dir, bootstrap_key):
    a, b = pair
    assert _ledger(client, a, a).status_code == 400        # same target twice
    assert _ledger(client, a, 9999).status_code == 404     # unknown target
    app = create_app()
    app.config.update(TESTING=True, DB_KEY=bootstrap_key)
    assert app.test_client().post(
        "/api/ledger", json={"target_a_id": a, "target_b_id": b}).status_code == 401


def test_deleting_a_target_cascades_its_saved_ledgers(client, pair):
    a, b = pair
    client.post("/api/ledger/save", json={"target_a_id": a, "target_b_id": b})
    assert client.delete(f"/api/targets/{a}").status_code == 200
    assert client.get("/api/ledger/saved").get_json()["data"] == []


# ---- export workbook integration ----

def test_export_pair_records_sheet_is_exhaustive(client, pair):
    """The workbook lists EVERY ledger row -- no cap. The 50-row cap is a UI
    affordance; the export is the exhaustive artifact."""
    a, b = pair
    saved = client.post("/api/ledger/save",
                        json={"target_a_id": a, "target_b_id": b}).get_json()["data"]
    wb = load_workbook(io.BytesIO(client.post("/api/export/results.xlsx").data))
    rows = list(wb["Pair records"].iter_rows(values_only=True))
    assert rows[0] == tuple(
        ["Ledger ID", "Dataset", "Pair", "Saved at", "Category", "Who", "Phone",
         "Date & time", "Call type", "Duration (s)", "Other party",
         "Other party name", "Also a target", "Area", "Distinctive"])
    assert not any("onfidence" in str(h) or "trength" in str(h) for h in rows[0])
    body = rows[1:]
    assert len(body) == saved["row_count"]          # every row, none dropped
    assert "A (100)" in body[0][2] and "B (200)" in body[0][2]

    direct = [r for r in body if r[4] == "Direct contact"]
    assert len(direct) == 4
    assert direct[0][7] == "2026-01-01 09:00"       # date AND time
    assert direct[0][8] == "out call (1)"           # wording (code) convention
    assert direct[0][11] == "B"                     # other party NAMED
    assert direct[0][12] == "yes"                   # ... and flagged as a target
    assert direct[0][14] == "—"                     # distinctive n/a on a direct row

    shared = [r for r in body if r[4] == "Shared contact"]
    assert {r[14] for r in shared} == {"distinctive"}
    assert any(r[4] == "Shared location" and r[13] == "Far" for r in body)


def test_export_pair_records_placeholder_when_nothing_saved(client):
    wb = load_workbook(io.BytesIO(client.post("/api/export/results.xlsx").data))
    rows = list(wb["Pair records"].iter_rows(values_only=True))
    assert rows[1][0] == "none saved"


def test_export_carries_saved_matches_and_tallies(client, pair):
    a, b = pair
    client.post("/api/match/save", json={"target_a_id": a, "target_b_id": b})
    client.post("/api/frequency/save", json={
        "target_id": a, "rank_by": "area", "hour_from": 8, "hour_to": 12})

    wb = load_workbook(io.BytesIO(client.post("/api/export/results.xlsx").data))
    matches = list(wb["Contact matches"].iter_rows(values_only=True))
    findings = {r[5]: r for r in matches[1:]}
    assert set(findings) == {"Direct contact", "Mutual relationship", "Meeting up"}
    assert findings["Direct contact"][6] == "Medium"
    assert "A (100)" in matches[1][2] and "B (200)" in matches[1][3]
    # Adaptive-gates columns: the dataset mode (with its classification
    # confidence) and any near-boundary cliff notes travel with every row.
    assert matches[0][10] == "Dataset mode" and matches[0][11] == "Near-boundary notes"
    assert findings["Direct contact"][10] == "strangers (High confidence)"
    # direct volume 4 sits one above DIRECT_MEDIUM=3 -> a "barely clears" note
    assert "barely clears Medium" in findings["Direct contact"][11]

    tallies = list(wb["Frequency counts"].iter_rows(values_only=True))
    assert len(tallies) > 1
    label = tallies[1][5]
    assert "Location / tower ranking" in label and "hours 08:00–12:59" in label
    # stored == exported: the sheet reads the saved tally, never recomputes
    saved = client.get("/api/frequency/saved").get_json()["data"][0]
    assert tallies[1][8] == saved["tally"]["top"][0]["value"]
    assert tallies[1][9] == saved["tally"]["top"][0]["count"]


def test_matcher_generator_outputs_are_repo_local():
    from tools import gen_matcher_scenarios as scenarios

    assert scenarios.STRANGERS_OUTPUT.parent == scenarios.REPO_ROOT
    assert scenarios.STRANGERS_OUTPUT.name == "sample_matcher_scenarios.xlsx"
    assert scenarios.CLOSEKNIT_OUTPUT.parent == scenarios.REPO_ROOT
    assert scenarios.CLOSEKNIT_OUTPUT.name == "sample_matcher_closeknit.xlsx"
