"""FlowDeck service: one object that owns the store, the live census and the read models.

The API, the AI assistant and the evaluations all go through this class, so
every number a person or the AI sees comes from the same code path.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from flowdeck.census.state import CLEAN, DIRTY, OCCUPIED, Census
from flowdeck.hl7.parser import Hl7ParseError, parse_adt
from flowdeck.ops import audit
from flowdeck.ops.forecast import forecast_unit
from flowdeck.store import Store

BARRIER_DEPTS = {
    "labs": "Laboratory",
    "imaging": "Radiology",
    "pharmacy": "Pharmacy",
    "transport": "Patient Transport",
    "case_mgmt": "Case Management",
    "family": "Nursing",
}
INPATIENT_UNITS_EXCLUDE = {"ED"}


class FlowDeck:
    def __init__(self, config: str | Path, store: Store | None = None) -> None:
        self.config = Path(config)
        self.store = store or Store()
        self.census = self._replay()

    # ---- ingestion --------------------------------------------------------
    def _replay(self, until: datetime | None = None) -> Census:
        census = Census.from_config(self.config)
        for raw in self.store.accepted_messages(until):
            census.apply(parse_adt(raw))
        if until:
            census.tick(until)
            census.as_of = until
        return census

    def ingest(self, raw: str) -> tuple[str, list, dict | None]:
        """Archive + apply one message. Returns (status, changed_beds, event_summary)."""
        try:
            ev = parse_adt(raw)
        except Hl7ParseError as exc:
            self.store.archive(raw, "rejected", error=str(exc))
            raise
        if self.store.has_control_id(ev.message_control_id):
            self.store.archive(raw, "duplicate", ev.message_control_id, ev.event_time, ev.trigger)
            return "duplicate", [], None
        self.store.archive(raw, "accepted", ev.message_control_id, ev.event_time, ev.trigger)
        changed = self.census.apply(ev)
        summary = {"time": ev.event_time.isoformat(), "trigger": ev.trigger, "kind": ev.kind,
                   "visit": ev.visit_number, "initials": ev.patient_initials,
                   "bed": ev.location.bed_id if ev.location else None,
                   "from": ev.prior_location.bed_id if ev.prior_location else None}
        return "accepted", changed, summary

    @property
    def now(self) -> datetime:
        """Operational 'now' = time of the latest event (simulated clock in demos)."""
        return self.census.as_of or datetime.now()

    def census_at(self, at: datetime | None) -> Census:
        return self.census if at is None or at >= self.now else self._replay(at)

    # ---- read models -----------------------------------------------------
    def overview(self, at: datetime | None = None) -> dict:
        c = self.census_at(at)
        now = c.as_of or self.now
        units = c.summary()
        inpatient = [u for u in units if u["unit"] not in INPATIENT_UNITS_EXCLUDE]
        tot = sum(u["total"] for u in inpatient)
        occ = sum(u[OCCUPIED] for u in inpatient)
        dcs = self.discharges(at)
        return {
            "as_of": now.isoformat(),
            "kpis": {
                "inpatient_occupancy_pct": round(100 * occ / tot, 1) if tot else 0,
                "inpatient_occupied": occ, "inpatient_total": tot,
                "clean_beds": sum(u[CLEAN] for u in inpatient),
                "dirty_beds": sum(u[DIRTY] for u in inpatient),
                "ed_boarding": len(c.boarding()),
                "expected_discharges_remaining": len(dcs),
                "discharges_ready": sum(1 for d in dcs if d["open_barriers"] == 0),
                "open_barriers": sum(d["open_barriers"] for d in dcs),
            },
            "units": units,
            "forecast": [f for f in self.forecast(8, at)],
        }

    def recent_events(self, limit: int = 40, at: datetime | None = None) -> list[dict]:
        sql = "SELECT event_time, trigger, raw FROM adt_messages WHERE status='accepted'"
        params: tuple = ()
        if at:
            sql += " AND event_time <= ?"
            params = (at.isoformat(),)
        rows = self.store.query(sql + " ORDER BY event_time DESC, id DESC LIMIT ?", (*params, limit))
        out = []
        for r in rows:
            ev = parse_adt(r["raw"])
            out.append({"time": ev.event_time.isoformat(), "trigger": ev.trigger, "kind": ev.kind,
                        "initials": ev.patient_initials, "visit": ev.visit_number,
                        "bed": ev.location.bed_id if ev.location else None,
                        "from": ev.prior_location.bed_id if ev.prior_location else None})
        return out

    def discharges(self, at: datetime | None = None) -> list[dict]:
        """Expected discharges still in a bed, with their barriers as of ``at``."""
        c = self.census_at(at)
        now = c.as_of or self.now
        expected = self.store.expected_discharge_visits(now)
        barriers: dict[str, list[dict]] = {}
        for b in self.store.barriers_as_of(now):
            barriers.setdefault(b["visit_number"], []).append(b)
        rows = []
        for visit in expected:
            bed_id = c.visits.get(visit)
            if not bed_id:
                continue  # already discharged
            bed = c.beds[bed_id]
            bs = barriers.get(visit, [])
            open_bs = [b for b in bs if b["is_open"]]
            for b in open_bs:
                b["minutes_open"] = int((now - datetime.fromisoformat(b["opened_at"])).total_seconds() // 60)
                b["dept_name"] = BARRIER_DEPTS.get(b["type"], b["owner_dept"])
            rows.append({"visit_number": visit, "bed_id": bed_id, "unit": bed.unit,
                         "patient_initials": bed.patient_initials, "open_barriers": len(open_bs),
                         "resolved_barriers": len(bs) - len(open_bs), "barriers": open_bs,
                         "oldest_barrier_minutes": max((b["minutes_open"] for b in open_bs), default=0)})
        return sorted(rows, key=lambda r: (-r["open_barriers"], -r["oldest_barrier_minutes"]))

    def open_barriers(self, dept: str | None = None, at: datetime | None = None) -> list[dict]:
        out = []
        for d in self.discharges(at):
            for b in d["barriers"]:
                if dept is None or b["type"] == dept:
                    out.append({**b, "bed_id": d["bed_id"], "unit": d["unit"],
                                "patient_initials": d["patient_initials"]})
        return sorted(out, key=lambda b: -b["minutes_open"])

    def admit_rate(self, c: Census, now: datetime, lookback_hours: int = 6) -> dict[str, float]:
        """Admit decisions per hour, by destination unit, over the lookback window."""
        since = (now - timedelta(hours=lookback_hours)).isoformat()
        rows = self.store.query(
            "SELECT raw FROM adt_messages WHERE status='accepted' AND trigger='A06' AND event_time > ? "
            "AND event_time <= ?", (since, now.isoformat()))
        counts: dict[str, int] = {}
        for r in rows:
            unit = c.service_to_unit(parse_adt(r["raw"]).hospital_service)
            if unit:
                counts[unit] = counts.get(unit, 0) + 1
        return {u: n / lookback_hours for u, n in counts.items()}

    def forecast(self, hours: int = 8, at: datetime | None = None) -> list[dict]:
        c = self.census_at(at)
        now = c.as_of or self.now
        boarding = c.boarding()
        rates = self.admit_rate(c, now)
        dcs = self.discharges(at)
        out = []
        for u in c.summary():
            if u["unit"] in INPATIENT_UNITS_EXCLUDE:
                continue
            f = forecast_unit(
                unit=u["unit"], total=u["total"], occupied_now=u[OCCUPIED],
                boarding_inbound=sum(1 for b in boarding if b["requested_unit"] == u["unit"]),
                admit_rate_per_hr=rates.get(u["unit"], 0.0),
                discharge_candidates=[d["open_barriers"] for d in dcs if d["unit"] == u["unit"]],
                now=now, hours=hours)
            out.append(f.as_dict())
        return out

    # ---- suggestions & decisions ------------------------------------------
    def refresh_suggestions(self) -> list[dict]:
        from flowdeck.ops.suggestions import generate
        for s in generate(self):
            self.store.upsert_suggestion(s)
        return self.store.suggestions()

    def decide(self, suggestion_id: int, decision: str, actor: str, note: str = "") -> dict:
        if decision not in ("approved", "rejected"):
            raise ValueError("decision must be 'approved' or 'rejected'")
        if not actor.strip():
            raise ValueError("A named person must make every decision")
        rows = self.store.query("SELECT * FROM suggestions WHERE id=?", (suggestion_id,))
        if not rows:
            raise KeyError(suggestion_id)
        if rows[0]["status"] != "pending":
            raise ValueError("Suggestion already decided")
        ts = self.now.isoformat(timespec="seconds")
        self.store.execute(
            "UPDATE suggestions SET status=?, decided_by=?, decided_at=?, decision_note=? WHERE id=?",
            (decision, actor.strip(), ts, note, suggestion_id))
        audit.append(self.store, actor, f"suggestion.{decision}",
                     {"suggestion_id": suggestion_id, "title": rows[0]["title"], "note": note}, self.now)
        return self.store.query("SELECT * FROM suggestions WHERE id=?", (suggestion_id,))[0]

    def resolve_barrier(self, barrier_id: int, actor: str) -> None:
        self.store.resolve_barrier(barrier_id, self.now)
        audit.append(self.store, actor, "barrier.resolved", {"barrier_id": barrier_id}, self.now)
