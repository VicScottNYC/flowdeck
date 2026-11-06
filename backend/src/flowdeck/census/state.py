"""Live census: applies ADT events to a model of the hospital's beds.

This is the heart of FlowDeck. The legacy HIS only *announces* changes;
FlowDeck keeps the current picture of every bed so screens can update live.

Bed lifecycle:  clean --admit--> occupied --discharge/transfer out--> dirty --(EVS)--> clean
ED boarding:    an ED patient with an admit decision (A06) who is still in an ED bed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from flowdeck.hl7.parser import AdtEvent

CLEAN, OCCUPIED, DIRTY = "clean", "occupied", "dirty"


@dataclass
class Bed:
    bed_id: str
    unit: str
    room: str
    bed: str
    status: str = CLEAN
    visit_number: str | None = None
    patient_initials: str | None = None
    patient_class: str | None = None
    since: str | None = None  # ISO timestamp of last status change
    admit_decision_at: str | None = None  # set while boarding
    requested_service: str | None = None  # where a boarding patient is headed


@dataclass
class Conflict:
    time: str
    message_control_id: str
    detail: str


@dataclass
class Census:
    units: dict[str, dict] = field(default_factory=dict)
    beds: dict[str, Bed] = field(default_factory=dict)
    visits: dict[str, str] = field(default_factory=dict)  # visit_number -> bed_id
    seen_control_ids: set[str] = field(default_factory=set)
    conflicts: list[Conflict] = field(default_factory=list)
    turnaround_minutes: int = 60
    as_of: datetime | None = None

    @classmethod
    def from_config(cls, path: str | Path) -> Census:
        """Build beds from config: rooms numbered from ``first_room``, beds A, B..."""
        config = json.loads(Path(path).read_text())
        census = cls()
        for unit in config["units"]:
            census.units[unit["code"]] = unit
            for r in range(unit["rooms"]):
                room = str(unit["first_room"] + r)
                for bed in "ABCD"[: unit["beds_per_room"]]:
                    b = Bed(bed_id=f"{unit['code']}-{room}-{bed}", unit=unit["code"], room=room, bed=bed)
                    census.beds[b.bed_id] = b
        return census

    def service_to_unit(self, service: str | None) -> str | None:
        for code, u in self.units.items():
            if u.get("service") == service:
                return code
        return None

    # ---- event handling -------------------------------------------------
    def apply(self, ev: AdtEvent) -> list[Bed]:
        """Apply one event. Returns the beds that changed (for live updates).

        Idempotent: the same MSH-10 control ID is applied only once, because
        legacy interfaces *will* resend messages after a timeout.
        """
        if ev.message_control_id in self.seen_control_ids:
            return []
        self.seen_control_ids.add(ev.message_control_id)
        changed = self.tick(ev.event_time)
        handler = {
            "admit": self._admit,
            "transfer": self._transfer,
            "discharge": self._discharge,
            "change_to_inpatient": self._admit_decision,
            "cancel_admit": self._cancel_admit,
            "cancel_discharge": self._admit,
            "update": lambda e: [],
        }[ev.kind]
        changed += handler(ev)
        self.as_of = max(self.as_of or ev.event_time, ev.event_time)
        return changed

    def tick(self, now: datetime) -> list[Bed]:
        """Environmental services model: a dirty bed turns clean after the turnaround.

        In a real deployment, EVS status comes from the housekeeping system or
        from ``POST /beds/{id}/status``; this keeps the simulated day realistic.
        """
        changed = []
        for bed in self.beds.values():
            if bed.status == DIRTY and bed.since:
                ready = datetime.fromisoformat(bed.since) + timedelta(minutes=self.turnaround_minutes)
                if now >= ready:
                    bed.status, bed.since = CLEAN, ready.isoformat()
                    changed.append(bed)
        return changed

    def _conflict(self, ev: AdtEvent, detail: str) -> None:
        self.conflicts.append(Conflict(ev.event_time.isoformat(), ev.message_control_id, detail))

    def _occupy(self, bed_id: str, ev: AdtEvent) -> list[Bed]:
        bed = self.beds.get(bed_id)
        if bed is None:
            self._conflict(ev, f"Unknown bed {bed_id}")
            return []
        if bed.status == OCCUPIED and bed.visit_number != ev.visit_number:
            # Never silently overwrite: flag it for the bed manager instead.
            self._conflict(ev, f"{bed_id} already occupied by another visit")
            return []
        bed.status = OCCUPIED
        bed.visit_number = ev.visit_number
        bed.patient_initials = ev.patient_initials
        bed.patient_class = ev.patient_class
        bed.since = ev.event_time.isoformat()
        bed.admit_decision_at = None
        bed.requested_service = None
        self.visits[ev.visit_number] = bed_id
        return [bed]

    def _vacate(self, bed_id: str | None, ev: AdtEvent, status: str) -> list[Bed]:
        bed = self.beds.get(bed_id or "")
        if bed is None:
            self._conflict(ev, f"Visit {ev.visit_number} not found in any bed")
            return []
        bed.status = status
        bed.visit_number = bed.patient_initials = bed.patient_class = None
        bed.admit_decision_at = bed.requested_service = None
        bed.since = ev.event_time.isoformat()
        return [bed]

    def _admit(self, ev: AdtEvent) -> list[Bed]:
        if ev.location is None:  # e.g. ED arrival with no bed yet
            return []
        return self._occupy(ev.location.bed_id, ev)

    def _admit_decision(self, ev: AdtEvent) -> list[Bed]:
        bed = self.beds.get(self.visits.get(ev.visit_number, ""))
        if bed is None:
            self._conflict(ev, f"Admit decision for unknown visit {ev.visit_number}")
            return []
        bed.patient_class = "I"
        bed.admit_decision_at = ev.event_time.isoformat()
        bed.requested_service = ev.hospital_service
        return [bed]

    def _transfer(self, ev: AdtEvent) -> list[Bed]:
        old = self.visits.get(ev.visit_number) or (ev.prior_location.bed_id if ev.prior_location else None)
        if ev.location is None:
            self._conflict(ev, "Transfer without a destination")
            return []
        target = self.beds.get(ev.location.bed_id)
        if target and target.status == OCCUPIED and target.visit_number != ev.visit_number:
            self._conflict(ev, f"Transfer target {ev.location.bed_id} is occupied")
            return []
        changed = self._vacate(old, ev, DIRTY) if old in self.beds else []
        return changed + self._occupy(ev.location.bed_id, ev)

    def _discharge(self, ev: AdtEvent) -> list[Bed]:
        bed_id = self.visits.pop(ev.visit_number, None) or (ev.location.bed_id if ev.location else None)
        return self._vacate(bed_id, ev, DIRTY)

    def _cancel_admit(self, ev: AdtEvent) -> list[Bed]:
        return self._vacate(self.visits.pop(ev.visit_number, None), ev, CLEAN)

    def mark_status(self, bed_id: str, status: str, when: datetime) -> Bed:
        """Housekeeping update (not an ADT event)."""
        bed = self.beds[bed_id]
        if bed.status == OCCUPIED:
            raise ValueError("Cannot change housekeeping status of an occupied bed")
        bed.status, bed.since = status, when.isoformat()
        return bed

    # ---- read models ----------------------------------------------------
    def summary(self) -> list[dict]:
        out = []
        for code, u in self.units.items():
            beds = [b for b in self.beds.values() if b.unit == code]
            counts = {s: sum(b.status == s for b in beds) for s in (CLEAN, OCCUPIED, DIRTY)}
            out.append({"unit": code, "name": u["name"], "total": len(beds), **counts,
                        "occupancy_pct": round(100 * counts[OCCUPIED] / len(beds), 1)})
        return out

    def boarding(self) -> list[dict]:
        now = self.as_of
        rows = []
        for b in self.beds.values():
            if b.admit_decision_at:
                waited = (now - datetime.fromisoformat(b.admit_decision_at)) if now else timedelta()
                rows.append({"bed_id": b.bed_id, "visit_number": b.visit_number,
                             "patient_initials": b.patient_initials,
                             "requested_unit": self.service_to_unit(b.requested_service),
                             "admit_decision_at": b.admit_decision_at,
                             "minutes_waiting": int(waited.total_seconds() // 60)})
        return sorted(rows, key=lambda r: -r["minutes_waiting"])

    def beds_json(self, unit: str | None = None) -> list[dict]:
        return [asdict(b) for b in self.beds.values() if unit is None or b.unit == unit]
