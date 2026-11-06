"""Tests for the store, read models, forecast, AI guardrails, audit chain, FHIR and API."""

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from fhir.resources.R4B.bundle import Bundle
from fhir.resources.R4B.encounter import Encounter

from flowdeck.assistant import tools
from flowdeck.assistant.engine import FoundryEngine, OfflineEngine, grounding_check
from flowdeck.demo import seed_demo
from flowdeck.fhir import mapper
from flowdeck.hl7.parser import Hl7ParseError
from flowdeck.ops import audit
from flowdeck.ops.forecast import discharge_probability, forecast_unit
from flowdeck.service import FlowDeck
from flowdeck.store import Store

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "simulator" / "hospital.json"
DAY = datetime(2026, 11, 6)


@pytest.fixture(scope="module")
def fd() -> FlowDeck:
    f = FlowDeck(CONFIG)
    seed_demo(f, seed=42, day=DAY, until="14:30")
    return f


# ---------- event store & replay ----------
def test_restart_rebuilds_identical_census(tmp_path):
    db = tmp_path / "flowdeck.db"
    a = FlowDeck(CONFIG, Store(db))
    seed_demo(a, seed=3, day=DAY, until="12:00")
    b = FlowDeck(CONFIG, Store(db))  # "restart": new process, same database
    b.census.tick(a.now)
    assert a.census.summary() == b.census.summary()


def test_duplicates_and_rejections_are_archived():
    f = FlowDeck(CONFIG)
    raw = __import__("simulate_day").simulate(1, DAY)[0]
    assert f.ingest(raw)[0] == "accepted"
    assert f.ingest(raw)[0] == "duplicate"
    with pytest.raises(Hl7ParseError):
        f.ingest("not hl7")
    assert f.store.message_stats() == {"accepted": 1, "duplicate": 1, "rejected": 1}


def test_time_travel_matches_live_census(fd):
    assert fd.census_at(fd.now).summary() == fd.census.summary()
    earlier = fd.overview(datetime(2026, 11, 6, 9, 0))
    assert earlier["as_of"].startswith("2026-11-06T09:00")


def test_occupied_bed_is_never_overwritten():
    f = FlowDeck(CONFIG)
    sim = __import__("simulate_day")
    msgs = [m for m in sim.simulate(2, DAY) if "ADT^A01" in m][:1]
    f.ingest(msgs[0])
    clash = msgs[0].replace(msgs[0].split("|")[9], "CLASH1", 1).replace("|V", "|VX", 1)
    f.ingest(clash)
    assert f.census.conflicts and "already occupied" in f.census.conflicts[0].detail


# ---------- discharges, barriers, boarding ----------
def test_discharge_view_hides_future_resolutions(fd):
    for d in fd.discharges():
        for b in d["barriers"]:
            assert b["is_open"] and b["resolved_at"] is None
            assert b["opened_at"] <= fd.now.isoformat()


def test_minimum_necessary_display(fd):
    for b in fd.census.beds_json():
        assert b["patient_initials"] is None or len(b["patient_initials"]) <= 2


# ---------- forecast ----------
def test_discharge_probability_bounds():
    assert discharge_probability(datetime(2026, 1, 1, 20), 4, 0) == 0.0  # window closed
    p_open = discharge_probability(datetime(2026, 1, 1, 10), 8, 0)
    p_blocked = discharge_probability(datetime(2026, 1, 1, 10), 8, 2)
    assert 0 < p_blocked < p_open <= 1


def test_forecast_is_clamped_to_capacity():
    f = forecast_unit("X", 10, 10, 5, 2.0, [], datetime(2026, 1, 1, 10), 8)
    assert f.predicted_occupied == 10 and f.predicted_pct == 100.0


# ---------- assistant guardrails ----------
def test_grounding_check_flags_invented_numbers():
    outputs = [{"kpis": {"clean_beds": 15, "pct": 87.5}}]
    assert grounding_check("There are 15 clean beds at 87.5%", outputs) == []
    assert grounding_check("There are 22 clean beds", outputs) == ["22"]
    assert grounding_check("As of 14:30 there are 15", outputs) == []  # times are not claims


def test_tools_are_read_only_and_cite_sources(fd):
    before = json.dumps(fd.overview(), sort_keys=True)
    for name in tools.TOOLS:
        out = tools.call(fd, name, {"unit": "4W"} if name == "get_unit" else {})
        assert "source" in out
    assert json.dumps(fd.overview(), sort_keys=True) == before


def test_offline_answers_are_grounded(fd):
    for q in ["How is 4W?", "Who is boarding?", "lab barriers?", "forecast 4 hours", "summary"]:
        a = OfflineEngine().ask(fd, q)
        assert a.grounded, (q, a.unverified_numbers)
        assert a.citations


def test_foundry_engine_tool_loop_with_fake_client(fd):
    calls = []

    class FakeResponses:
        def create(self, **kw):
            calls.append(kw)
            if len(calls) == 1:
                fc = SimpleNamespace(type="function_call", name="get_hospital_overview", arguments="{}", call_id="c1")
                return SimpleNamespace(id="r1", output=[fc], output_text="")
            k = fd.overview()["kpis"]
            return SimpleNamespace(id="r2", output=[], output_text=f"Occupancy is {k['inpatient_occupancy_pct']}%.")

    a = FoundryEngine(client=SimpleNamespace(responses=FakeResponses()), model="test").ask(fd, "status?")
    assert a.engine == "foundry" and a.grounded
    assert calls[1]["previous_response_id"] == "r1"
    assert "<tool_output>" in calls[1]["input"][0]["output"]


# ---------- approvals & audit ----------
def test_decisions_need_a_named_person_and_are_chained():
    f = FlowDeck(CONFIG)
    seed_demo(f, seed=42, day=DAY, until="14:30")
    s = f.store.suggestions()[0]
    with pytest.raises(ValueError):
        f.decide(s["id"], "approved", "  ")
    f.decide(s["id"], "approved", "Dana Lee, Bed Manager")
    with pytest.raises(ValueError):
        f.decide(s["id"], "rejected", "Someone Else")  # can't decide twice
    assert audit.verify(f.store)["valid"]


def test_audit_tampering_is_detected():
    s = Store()
    for i in range(4):
        audit.append(s, "tester", "x", {"i": i})
    s.execute("UPDATE audit_log SET payload='{\"i\": 99}' WHERE seq=2")
    assert audit.verify(s) == {"valid": False, "entries": 4, "broken_at": 2}


# ---------- FHIR ----------
def test_fhir_encounter_and_locations_validate(fd):
    visit = fd.discharges()[0]["visit_number"]
    enc = {k: v for k, v in mapper.encounter(fd, visit).items() if v is not None}
    Encounter.model_validate(enc)
    assert "MRN" not in json.dumps(enc)  # pseudonymous subject only
    Bundle.model_validate(mapper.bundle(mapper.locations(fd)))


# ---------- API ----------
def test_api_smoke():
    from flowdeck.main import app

    with TestClient(app) as c:
        assert c.get("/api/health").json()["status"] == "ok"
        assert c.get("/api/overview").json()["kpis"]["inpatient_total"] == 152
        assert c.get("/api/units/4w/beds").status_code == 200
        assert c.get("/api/units/zz/beds").status_code == 404
        ans = c.post("/api/assistant/ask", json={"question": "summary"}).json()
        assert ans["grounded"]
        sid = c.get("/api/suggestions").json()[0]["id"]
        assert c.post(f"/api/suggestions/{sid}/approve", json={"actor": ""}).status_code == 422
        assert c.post(f"/api/suggestions/{sid}/approve", json={"actor": "QA"}).json()["status"] == "approved"
        assert c.get("/api/audit").json()["verification"]["valid"]
