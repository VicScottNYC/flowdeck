import asyncio
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "simulator"))

from simulate_day import simulate  # noqa: E402

from flowdeck.census.state import CLEAN, DIRTY, OCCUPIED, Census  # noqa: E402
from flowdeck.hl7 import mllp  # noqa: E402
from flowdeck.hl7.parser import Hl7ParseError, parse_adt  # noqa: E402

CONFIG = ROOT / "simulator" / "hospital.json"

ADMIT = "\r".join([
    "MSH|^~\\&|LEGACYHIS|MERIDIAN|FLOWDECK|MERIDIAN|20261106083000||ADT^A01^ADT_A01|MSG0001|P|2.5.1",
    "EVN|A01|20261106083000",
    "PID|1||MRN123456^^^MERIDIAN^MR||THORNE^AVERY||19600101|U",
    "PV1|1|I|4W^401^A^MERIDIAN||||1001^RIVERA^SAM|||MED|||||||||V12345678",
])
TRANSFER = ADMIT.replace("ADT^A01^ADT_A01|MSG0001", "ADT^A02^ADT_A02|MSG0002") \
    .replace("EVN|A01|20261106083000", "EVN|A02|20261106100000") \
    .replace("4W^401^A^MERIDIAN||||", "5E^501^B^MERIDIAN|||4W^401^A^MERIDIAN|")
DISCHARGE = TRANSFER.replace("ADT^A02^ADT_A02|MSG0002", "ADT^A03^ADT_A03|MSG0003") \
    .replace("EVN|A02|20261106100000", "EVN|A03|20261106150000")


# ---------- parser ----------
def test_parse_admit_fields():
    ev = parse_adt(ADMIT)
    assert ev.kind == "admit" and ev.trigger == "A01"
    assert ev.location.bed_id == "4W-401-A"
    assert ev.visit_number == "V12345678"
    assert ev.event_time == datetime(2026, 11, 6, 8, 30)
    assert ev.patient_initials == "AT"  # given + family initial, never the full name


def test_parse_transfer_prior_location():
    ev = parse_adt(TRANSFER)
    assert ev.kind == "transfer"
    assert ev.prior_location.bed_id == "4W-401-A"
    assert ev.location.bed_id == "5E-501-B"


@pytest.mark.parametrize("bad", ["", "PID|1", ADMIT.replace("ADT^A01", "ORU^R01"),
                                 ADMIT.replace("|MSG0001|", "||")])
def test_parse_rejects_bad_messages(bad):
    with pytest.raises(Hl7ParseError):
        parse_adt(bad)


# ---------- census ----------
def test_admit_transfer_discharge_lifecycle():
    c = Census.from_config(CONFIG)
    c.apply(parse_adt(ADMIT))
    assert c.beds["4W-401-A"].status == OCCUPIED
    c.apply(parse_adt(TRANSFER))
    assert c.beds["4W-401-A"].status == DIRTY
    assert c.beds["5E-501-B"].status == OCCUPIED
    c.apply(parse_adt(DISCHARGE))
    assert c.beds["5E-501-B"].status == DIRTY
    assert c.beds["4W-401-A"].status == CLEAN  # turned over by the cleaning stand-in


def test_duplicate_messages_are_ignored():
    c = Census.from_config(CONFIG)
    assert c.apply(parse_adt(ADMIT))
    assert c.apply(parse_adt(ADMIT)) == []  # legacy interfaces resend; stay idempotent


# ---------- MLLP ----------
def test_mllp_frame_roundtrip():
    msgs, rest = mllp.unframe(mllp.frame("A") + mllp.frame("B") + b"\x0bpartial")
    assert msgs == ["A", "B"] and rest == b"\x0bpartial"


def test_mllp_end_to_end_ack():
    received = []

    async def run():
        async def handler(raw):
            received.append(parse_adt(raw))
        server = await mllp.serve(handler, host="127.0.0.1", port=0)
        port = server.sockets[0].getsockname()[1]
        async with server:
            acks = await mllp.send([ADMIT, "MSH|^~\\&|X|Y|Z|W|20261106||ADT^Z99|BAD1|P|2.5.1"],
                                   port=port)
        return acks

    acks = asyncio.run(run())
    assert "MSA|AA|MSG0001" in acks[0]
    assert "MSA|AE|BAD1" in acks[1]
    assert received[0].visit_number == "V12345678"


# ---------- simulator ----------
def test_simulated_day_never_double_books_a_bed():
    c = Census.from_config(CONFIG)
    msgs = simulate(seed=7, day=datetime(2026, 11, 6))
    assert len(msgs) > 100
    for raw in msgs:
        ev = parse_adt(raw)
        if ev.kind in ("admit", "transfer") and ev.location:
            assert c.beds[ev.location.bed_id].status != OCCUPIED, f"double-booked {ev.location.bed_id}"
        c.apply(ev)
    assert all(0 <= u["occupancy_pct"] <= 100 for u in c.summary())


def test_simulator_is_deterministic():
    day = datetime(2026, 11, 6)
    assert simulate(seed=1, day=day) == simulate(seed=1, day=day)
