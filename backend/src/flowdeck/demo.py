"""Demo seeding: load a simulated day into FlowDeck.

ADT messages come from the simulator (the "legacy HIS"). Discharge plans and
barriers are FlowDeck's own data, entered by departments in real life; here
they are generated from the same seed so the demo is reproducible.
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flowdeck.hl7.parser import parse_adt
from flowdeck.service import BARRIER_DEPTS, FlowDeck

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "simulator"))

NOTES = {
    "labs": ["Awaiting final CBC", "Pending BMP before discharge", "Culture result outstanding"],
    "imaging": ["Follow-up X-ray read pending", "Echo not yet performed", "CT read pending"],
    "pharmacy": ["Discharge med reconciliation", "Prior auth for anticoagulant", "Meds-to-beds delivery"],
    "transport": ["Wheelchair van to home", "Ambulance to SNF not booked", "Ride confirmation pending"],
    "case_mgmt": ["SNF bed acceptance pending", "Home health referral", "Insurance authorization"],
    "family": ["Family pickup time not confirmed", "Caregiver teaching incomplete"],
}
TYPES = list(NOTES)
WEIGHTS = [3, 2, 3, 3, 2, 1]


def plan_operations(seed: int, messages: list[str], day: datetime) -> tuple[list[tuple], list[tuple]]:
    """Return (expected_discharges, barriers) derived from a full simulated day."""
    rng = random.Random(seed * 7919)
    morning_inpatients: dict[str, str] = {}
    discharged_at: dict[str, datetime] = {}
    for raw in messages:
        ev = parse_adt(raw)
        if ev.kind == "admit" and ev.patient_class == "I" and ev.event_time < day:
            morning_inpatients[ev.visit_number] = ev.location.unit if ev.location else ""
        if ev.kind == "discharge" and ev.visit_number in morning_inpatients:
            discharged_at[ev.visit_number] = ev.event_time

    flagged = day + timedelta(hours=7)
    expected, barriers = [], []

    for visit, t_dc in discharged_at.items():
        expected.append((visit, flagged))
        if rng.random() < 0.65:
            for type_ in sorted(set(rng.choices(TYPES, WEIGHTS, k=rng.randint(1, 3)))):
                opened = flagged + timedelta(minutes=rng.randint(0, 150))
                latest = t_dc - timedelta(minutes=15)
                if latest <= opened:
                    opened = latest - timedelta(minutes=30)
                resolved = opened + (latest - opened) * rng.uniform(0.3, 1.0)
                barriers.append((visit, type_, rng.choice(NOTES[type_]), opened, resolved))

    # Patients expected to go home today who will not, because something is stuck.
    stuck = [v for v in morning_inpatients if v not in discharged_at]
    rng.shuffle(stuck)
    for visit in stuck[:12]:
        expected.append((visit, flagged))
        for type_ in sorted(set(rng.choices(TYPES, WEIGHTS, k=rng.randint(1, 2)))):
            opened = flagged + timedelta(minutes=rng.randint(0, 240))
            barriers.append((visit, type_, rng.choice(NOTES[type_]), opened, None))
    return expected, barriers


def seed_demo(fd: FlowDeck, seed: int = 42, day: datetime | None = None, until: str | None = "14:30") -> dict:
    from simulate_day import simulate

    day = day or datetime(2026, 11, 6)
    full = simulate(seed, day)
    cutoff = datetime.combine(day, datetime.strptime(until, "%H:%M").time()) if until else None
    loaded = 0
    for raw in full:
        if cutoff and parse_adt(raw).event_time > cutoff:
            break
        fd.ingest(raw)
        loaded += 1
    expected, barriers = plan_operations(seed, full, day)
    for visit, at in expected:
        fd.store.flag_expected_discharge(visit, at)
    for visit, type_, note, opened, resolved in barriers:
        fd.store.add_barrier(visit, type_, BARRIER_DEPTS[type_], opened, note, resolved)
    if cutoff:
        fd.census.tick(cutoff)
        fd.census.as_of = cutoff
    fd.refresh_suggestions()
    return {"messages_loaded": loaded, "messages_in_day": len(full), "expected_discharges": len(expected),
            "barriers": len(barriers), "as_of": fd.now.isoformat()}
