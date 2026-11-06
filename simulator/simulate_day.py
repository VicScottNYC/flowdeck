"""Simulate one day of HL7 v2 ADT traffic for the fictional Meridian General.

Usage:
    python simulator/simulate_day.py --out simulator/out/day1.hl7           # write a file
    python simulator/simulate_day.py --send --speed 60                      # stream to FlowDeck via MLLP

Everything is synthetic. Names come from a small invented list; MRNs and visit
numbers are random. Seeded, so the same --seed always produces the same day,
which is what makes the simulator usable as ground truth for evaluations.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).parent
FIRST = ["Avery", "Jordan", "Riley", "Morgan", "Casey", "Quinn", "Rowan", "Sage", "Emery", "Reese",
         "Harper", "Logan", "Parker", "Skyler", "Dakota", "Finley", "Hayden", "Kendall", "Lennon", "Marlow"]
LAST = ["Alder", "Brook", "Calder", "Dunmore", "Ellery", "Fenwick", "Garrow", "Hollis", "Ivers", "Jessup",
        "Kestrel", "Lowell", "Marsh", "Northam", "Oakes", "Pruitt", "Quill", "Rendell", "Stroud", "Thorne"]
INPATIENT_UNITS = ["ICU", "4W", "5E", "6N", "7S"]


@dataclass
class Visit:
    visit_number: str
    mrn: str
    family: str
    given: str
    bed: str | None = None


def pl(bed_id: str | None, facility: str) -> str:
    if not bed_id:
        return ""
    unit, room, bed = bed_id.split("-")
    return f"{unit}^{room}^{bed}^{facility}"


def build_adt(trigger: str, ts: datetime, seq: int, v: Visit, patient_class: str,
              location: str | None, prior: str | None, service: str, facility: str) -> str:
    t = ts.strftime("%Y%m%d%H%M%S")
    pv1 = [""] * 46
    pv1[0], pv1[1], pv1[2] = "PV1", "1", patient_class
    pv1[3] = pl(location, facility)
    pv1[6] = pl(prior, facility)
    pv1[7] = "1001^RIVERA^SAM^^^DR"
    pv1[10] = service
    pv1[19] = v.visit_number
    pv1[44] = t
    if trigger == "A03":
        pv1[45] = t
    return "\r".join([
        f"MSH|^~\\&|LEGACYHIS|{facility}|FLOWDECK|{facility}|{t}||ADT^{trigger}^ADT_{trigger}|SIM{seq:06d}|P|2.5.1",
        f"EVN|{trigger}|{t}",
        f"PID|1||{v.mrn}^^^{facility}^MR||{v.family}^{v.given}||19600101|U",
        "|".join(pv1).rstrip("|"),
    ])


def simulate(seed: int, day: datetime, start_occupancy: float = 0.93,
             until: datetime | None = None) -> list[str]:
    rng = random.Random(seed)
    cfg = json.loads((HERE / "hospital.json").read_text())
    fac = cfg["facility"]
    units = {u["code"]: u for u in cfg["units"]}
    beds = {code: [f"{code}-{u['first_room'] + r}-{b}" for r in range(u["rooms"])
                   for b in "ABCD"[: u["beds_per_room"]]] for code, u in units.items()}
    # Each bed is available from a point in time; None = occupied indefinitely.
    available: dict[str, datetime | None] = {b: day - timedelta(days=7) for ids in beds.values() for b in ids}
    CLEANING = timedelta(minutes=60)

    def take_bed(unit: str, at: datetime) -> str | None:
        options = [b for b in beds[unit] if available[b] is not None and available[b] <= at]
        if not options:
            return None
        bed = rng.choice(options)
        available[bed] = None
        return bed

    def release_bed(bed: str, at: datetime) -> None:
        available[bed] = at + CLEANING

    messages: list[tuple[datetime, str]] = []
    seq = 0

    def new_visit() -> Visit:
        return Visit(visit_number=f"V{rng.randint(10_000_000, 99_999_999)}",
                     mrn=f"MRN{rng.randint(100_000, 999_999)}",
                     family=rng.choice(LAST).upper(), given=rng.choice(FIRST).upper())

    def emit(trigger, ts, v, cls, loc, prior, unit):
        nonlocal seq
        seq += 1
        messages.append((ts, build_adt(trigger, ts, seq, v, cls, loc, prior, units[unit]["service"], fac)))

    # 1) Morning snapshot: patients already in house (admitted before today)
    inpatients: list[tuple[Visit, str]] = []
    for code in INPATIENT_UNITS:
        for _ in range(int(len(beds[code]) * start_occupancy)):
            v = new_visit()
            admitted = day - timedelta(hours=rng.randint(12, 96))
            v.bed = take_bed(code, admitted)
            emit("A01", admitted, v, "I", v.bed, None, code)
            inpatients.append((v, code))

    # 2) Discharges: most happen mid-afternoon, a classic bottleneck. Bed frees
    #    up after cleaning, which is why morning ED admits wait.
    rng.shuffle(inpatients)
    for v, code in inpatients[: int(len(inpatients) * 0.22)]:
        ts = day + timedelta(hours=rng.triangular(9, 19, 14), minutes=rng.randint(0, 59))
        emit("A03", ts, v, "I", v.bed, None, code)
        release_bed(v.bed, ts)

    # 3) ED arrivals all day (processed in time order); about 30% admitted upstairs.
    #    If no inpatient bed is ready, the patient "boards" in the ED and we retry
    #    every 30 minutes, which is exactly the delay FlowDeck should surface.
    arrivals = sorted(day + timedelta(hours=rng.triangular(0, 23.5, 13)) for _ in range(rng.randint(85, 105)))
    for arrive in arrivals:
        ed_bed = take_bed("ED", arrive)
        if ed_bed is None:
            continue  # ED full; a real system would log a diversion
        v = new_visit()
        v.bed = ed_bed
        emit("A01", arrive, v, "E", ed_bed, None, "ED")
        ready = arrive + timedelta(hours=rng.uniform(2, 6))
        if rng.random() < 0.34:
            target = rng.choices(INPATIENT_UNITS, weights=[1, 4, 3, 2, 1])[0]
            # A06 = decision to admit; patient becomes inpatient but stays in the ED bed
            emit("A06", ready, v, "I", ed_bed, None, target)
            t, bed = ready + timedelta(minutes=rng.randint(20, 60)), None
            while bed is None and t < day + timedelta(days=1, hours=12):
                bed = take_bed(target, t)
                t = t if bed else t + timedelta(minutes=30)
            if bed is None:
                available[ed_bed] = None  # still boarding at end of simulation
                continue
            v.bed = bed
            emit("A02", t, v, "I", bed, ed_bed, target)
            release_bed(ed_bed, t)
        else:
            emit("A03", ready, v, "E", ed_bed, None, "ED")
            release_bed(ed_bed, ready)

    messages.sort(key=lambda m: m[0])
    return [m for ts, m in messages if until is None or ts <= until]


async def stream(msgs: list[str], speed: float, host: str, port: int) -> None:
    sys.path.insert(0, str(HERE.parent / "backend" / "src"))
    from flowdeck.hl7.mllp import send
    from flowdeck.hl7.parser import parse_adt

    prev = None
    for m in msgs:
        ts = parse_adt(m).event_time
        if prev and speed > 0:
            await asyncio.sleep(max(0.0, (ts - prev).total_seconds() / speed / 60))
        prev = ts
        ack = (await send([m], host, port))[0]
        status = ack.split("MSA|")[1][:2]
        print(f"{ts:%H:%M} {m.split('|')[8]:<16} {status}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--until", help="stop at this simulated time, e.g. 14:30")
    p.add_argument("--out", help="write messages to this .hl7 file")
    p.add_argument("--send", action="store_true", help="stream to the MLLP listener")
    p.add_argument("--speed", type=float, default=60, help="60 = one simulated hour per real minute")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=2575)
    a = p.parse_args()

    day = datetime.strptime(a.date, "%Y-%m-%d")
    until = datetime.combine(day, datetime.strptime(a.until, "%H:%M").time()) if a.until else None
    msgs = simulate(a.seed, day, until=until)
    print(f"Generated {len(msgs)} ADT messages for {a.date} (seed {a.seed})")
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text("\n\n".join(msgs).replace("\r", "\n") + "\n")
        print(f"Wrote {a.out}")
    if a.send:
        asyncio.run(stream(msgs, a.speed, a.host, a.port))


if __name__ == "__main__":
    main()
