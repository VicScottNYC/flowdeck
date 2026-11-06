"""Minimal HL7 v2 parser for ADT messages.

Legacy hospital systems announce admits, transfers and discharges as HL7 v2
messages. This module turns one raw message into a typed ``AdtEvent``.

It is intentionally small and dependency-free so you can read every line.
Field numbering follows the HL7 spec (1-based). MSH is special: MSH-1 *is*
the field separator, so MSH-n lives at index n-1 after splitting.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

SUPPORTED_EVENTS = {
    "A01": "admit",
    "A02": "transfer",
    "A03": "discharge",
    "A06": "change_to_inpatient",
    "A08": "update",
    "A11": "cancel_admit",
    "A13": "cancel_discharge",
}


class Hl7ParseError(ValueError):
    """Raised when a message is malformed or missing a required field."""


@dataclass(frozen=True)
class Location:
    unit: str
    room: str
    bed: str

    @property
    def bed_id(self) -> str:
        return f"{self.unit}-{self.room}-{self.bed}"

    @classmethod
    def from_pl(cls, value: str, component_sep: str = "^") -> Location | None:
        """Parse an HL7 PL (person location) field: unit^room^bed^facility."""
        if not value:
            return None
        parts = value.split(component_sep) + ["", "", ""]
        unit, room, bed = parts[0], parts[1], parts[2]
        if not unit:
            return None
        return cls(unit=unit, room=room, bed=bed)


@dataclass(frozen=True)
class AdtEvent:
    message_control_id: str
    trigger: str  # e.g. "A01"
    kind: str  # e.g. "admit"
    event_time: datetime
    mrn: str
    visit_number: str
    patient_class: str  # I = inpatient, E = emergency, O = outpatient
    location: Location | None
    prior_location: Location | None
    hospital_service: str
    attending: str
    patient_initials: str  # minimum-necessary display; never the full name


def _parse_ts(value: str) -> datetime:
    """HL7 timestamps look like YYYYMMDDHHMM[SS]."""
    value = value.split("+")[0].split("-")[0].split(".")[0]
    formats = {14: "%Y%m%d%H%M%S", 12: "%Y%m%d%H%M", 8: "%Y%m%d"}
    fmt = formats.get(len(value))
    if fmt is None:
        raise Hl7ParseError(f"Bad HL7 timestamp: {value!r}")
    try:
        return datetime.strptime(value, fmt)
    except ValueError as exc:
        raise Hl7ParseError(f"Bad HL7 timestamp: {value!r}") from exc


def _segments(raw: str) -> dict[str, list[str]]:
    lines = [s for s in raw.replace("\r\n", "\r").replace("\n", "\r").split("\r") if s.strip()]
    if not lines or not lines[0].startswith("MSH"):
        raise Hl7ParseError("Message must start with an MSH segment")
    field_sep = lines[0][3]
    segs: dict[str, list[str]] = {}
    for line in lines:
        fields = line.split(field_sep)
        segs.setdefault(fields[0], fields)  # first occurrence wins
    return segs


def _get(fields: list[str], n: int) -> str:
    return fields[n] if n < len(fields) else ""


def parse_adt(raw: str) -> AdtEvent:
    segs = _segments(raw)
    msh = segs["MSH"]
    encoding = _get(msh, 1)  # MSH-2
    comp = encoding[0] if encoding else "^"

    # MSH-9 message type, e.g. ADT^A01^ADT_A01  (index 8 because of MSH quirk)
    msg_type = _get(msh, 8).split(comp)
    if not msg_type or msg_type[0] != "ADT" or len(msg_type) < 2:
        raise Hl7ParseError(f"Not an ADT message: {_get(msh, 8)!r}")
    trigger = msg_type[1]
    if trigger not in SUPPORTED_EVENTS:
        raise Hl7ParseError(f"Unsupported ADT trigger: {trigger}")

    control_id = _get(msh, 9)  # MSH-10
    if not control_id:
        raise Hl7ParseError("MSH-10 message control ID is required")

    pid = segs.get("PID")
    pv1 = segs.get("PV1")
    if pid is None or pv1 is None:
        raise Hl7ParseError("ADT message requires PID and PV1 segments")

    evn = segs.get("EVN")
    ts_raw = _get(evn, 2) if evn else ""  # EVN-2 recorded date/time
    event_time = _parse_ts(ts_raw or _get(msh, 6))  # fall back to MSH-7

    mrn = _get(pid, 3).split(comp)[0]  # PID-3 first identifier
    name = _get(pid, 5).split(comp)  # PID-5 family^given
    initials = "".join(p[:1].upper() for p in (name[1:2] + name[:1]) if p)

    return AdtEvent(
        message_control_id=control_id,
        trigger=trigger,
        kind=SUPPORTED_EVENTS[trigger],
        event_time=event_time,
        mrn=mrn,
        visit_number=_get(pv1, 19).split(comp)[0],  # PV1-19
        patient_class=_get(pv1, 2),  # PV1-2
        location=Location.from_pl(_get(pv1, 3), comp),  # PV1-3
        prior_location=Location.from_pl(_get(pv1, 6), comp),  # PV1-6
        hospital_service=_get(pv1, 10),  # PV1-10
        attending=_get(pv1, 7).split(comp)[1] if comp in _get(pv1, 7) else _get(pv1, 7),
        patient_initials=initials,
    )
