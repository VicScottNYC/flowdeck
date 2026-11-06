"""HL7 v2 ADT history -> FHIR R4 Encounter + Location resources.

FlowDeck's own mapper, kept small and readable. At L4 we compare it with
Azure Health Data Services' ``$convert-data`` (see ADR 004).

Privacy: the Patient reference is a pseudonymous hash of the MRN; no name,
birth date or MRN leaves this module.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

from flowdeck.hl7.parser import AdtEvent, parse_adt
from flowdeck.service import FlowDeck

TZ = ZoneInfo("America/New_York")
ACT_CODE = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
LOC_TYPE = "http://terminology.hl7.org/CodeSystem/location-physical-type"
CLASS_MAP = {"I": ("IMP", "inpatient encounter"), "E": ("EMER", "emergency"), "O": ("AMB", "ambulatory")}


def _ts(dt: datetime) -> str:
    return dt.replace(tzinfo=TZ).isoformat()


def pseudonym(mrn: str) -> str:
    return hashlib.sha256(f"flowdeck:{mrn}".encode()).hexdigest()[:16]


def visit_events(fd: FlowDeck, visit: str) -> list[AdtEvent]:
    rows = fd.store.query("SELECT raw FROM adt_messages WHERE status='accepted' AND raw LIKE ? "
                          "ORDER BY event_time, id", (f"%|{visit}%",))
    return [e for e in (parse_adt(r["raw"]) for r in rows) if e.visit_number == visit]


def encounter(fd: FlowDeck, visit: str) -> dict:
    events = visit_events(fd, visit)
    if not events:
        raise KeyError(visit)
    locations: list[dict] = []
    status, cls = "in-progress", events[0].patient_class
    for ev in events:
        if ev.kind in ("admit", "transfer") and ev.location:
            if locations:
                locations[-1]["status"] = "completed"
                locations[-1]["period"]["end"] = _ts(ev.event_time)
            locations.append({"location": {"reference": f"Location/{ev.location.bed_id}",
                                           "display": ev.location.bed_id},
                              "status": "active", "period": {"start": _ts(ev.event_time)}})
        if ev.kind == "change_to_inpatient":
            cls = "I"
        if ev.kind == "transfer":
            cls = ev.patient_class or cls
        if ev.kind == "discharge":
            status = "finished"
            if locations:
                locations[-1]["status"] = "completed"
                locations[-1]["period"]["end"] = _ts(ev.event_time)
    code, display = CLASS_MAP.get(cls, CLASS_MAP["I"])
    period = {"start": _ts(events[0].event_time)}
    if status == "finished":
        period["end"] = _ts(events[-1].event_time)
    return {
        "resourceType": "Encounter",
        "id": visit,
        "identifier": [{"system": "urn:flowdeck:visit", "value": visit}],
        "status": status,
        "class": {"system": ACT_CODE, "code": code, "display": display},
        "subject": {"reference": f"Patient/{pseudonym(events[0].mrn)}"},
        "period": period,
        "location": locations,
        "serviceType": {"text": events[-1].hospital_service} if events[-1].hospital_service else None,
    }


def locations(fd: FlowDeck) -> list[dict]:
    out = []
    for code, unit in fd.census.units.items():
        out.append({"resourceType": "Location", "id": code, "name": unit["name"], "status": "active",
                    "mode": "instance",
                    "physicalType": {"coding": [{"system": LOC_TYPE, "code": "wa", "display": "Ward"}]}})
    for b in fd.census.beds.values():
        out.append({"resourceType": "Location", "id": b.bed_id, "name": f"{b.unit} {b.room}{b.bed}",
                    "status": "active", "mode": "instance",
                    "operationalStatus": {"system": "http://terminology.hl7.org/CodeSystem/v2-0116",
                                          "code": {"clean": "U", "occupied": "O", "dirty": "K"}[b.status],
                                          "display": {"clean": "Unoccupied", "occupied": "Occupied",
                                                      "dirty": "Contaminated"}[b.status]},
                    "physicalType": {"coding": [{"system": LOC_TYPE, "code": "bd", "display": "Bed"}]},
                    "partOf": {"reference": f"Location/{b.unit}"}})
    return out


def bundle(resources: list[dict]) -> dict:
    return {"resourceType": "Bundle", "type": "collection",
            "entry": [{"resource": {k: v for k, v in r.items() if v is not None}} for r in resources]}
