"""Read-only tools for the ops assistant.

Rules enforced here, not in the prompt:
  * Read-only: no tool can change anything.
  * Minimum necessary: outputs carry bed IDs, initials and status only.
  * Every output has a ``source`` so answers can cite where a number came from.
"""

from __future__ import annotations

from flowdeck.service import FlowDeck


def _src(fd: FlowDeck, name: str) -> str:
    return f"{name}@{fd.now:%H:%M}"


def get_hospital_overview(fd: FlowDeck) -> dict:
    o = fd.overview()
    return {"source": _src(fd, "overview"), "as_of": o["as_of"], "kpis": o["kpis"],
            "units": [{k: u[k] for k in ("unit", "name", "total", "occupied", "clean", "dirty", "occupancy_pct")}
                      for u in o["units"]]}


def get_unit(fd: FlowDeck, unit: str) -> dict:
    unit = unit.upper()
    s = next((u for u in fd.census.summary() if u["unit"] == unit), None)
    if s is None:
        return {"source": _src(fd, "unit"), "error": f"Unknown unit {unit}",
                "known_units": list(fd.census.units)}
    dcs = [{k: d[k] for k in ("bed_id", "patient_initials", "open_barriers")}
           for d in fd.discharges() if d["unit"] == unit]
    fc = {f["hours"]: f for h in (4, 8) for f in fd.forecast(h) if f["unit"] == unit}
    return {"source": _src(fd, f"unit:{unit}"), "summary": s,
            "forecast": {f"{h}h": {"predicted_occupied": f["predicted_occupied"], "predicted_pct": f["predicted_pct"]}
                         for h, f in fc.items()},
            "discharges_expected": dcs, "discharges_expected_count": len(dcs),
            "discharges_ready_count": sum(1 for d in dcs if d["open_barriers"] == 0)}


def get_ed_boarding(fd: FlowDeck) -> dict:
    patients = fd.census.boarding()
    return {"source": _src(fd, "boarding"), "count": len(patients), "patients": patients}


def get_open_barriers(fd: FlowDeck, department: str | None = None) -> dict:
    items = fd.open_barriers(department)
    return {"source": _src(fd, f"barriers:{department or 'all'}"), "count": len(items),
            "barriers": [{k: b[k] for k in ("id", "type", "dept_name", "bed_id", "unit", "patient_initials",
                                            "minutes_open", "note")} for b in items]}


def get_forecast(fd: FlowDeck, hours: int = 8) -> dict:
    hours = max(1, min(int(hours), 24))
    return {"source": _src(fd, f"forecast:{hours}h"), "hours": hours, "units": fd.forecast(hours)}


TOOLS = {
    "get_hospital_overview": (get_hospital_overview, "Hospital-wide KPIs and per-unit bed counts.", {}),
    "get_unit": (get_unit, "Details for one unit: bed counts, 4h/8h forecast, expected discharges.",
                 {"unit": {"type": "string", "description": "Unit code, e.g. 4W, 5E, ICU, ED"}}),
    "get_ed_boarding": (get_ed_boarding, "ED patients with an admit decision still waiting for a bed.", {}),
    "get_open_barriers": (get_open_barriers, "Open discharge barriers, optionally for one department.",
                          {"department": {"type": "string", "enum": ["labs", "imaging", "pharmacy", "transport",
                                                                     "case_mgmt", "family"]}}),
    "get_forecast": (get_forecast, "Occupancy forecast for every inpatient unit.",
                     {"hours": {"type": "integer", "description": "Hours ahead, 1-24"}}),
}


def tool_specs() -> list[dict]:
    """Function-tool definitions in Responses API format."""
    return [{"type": "function", "name": name, "description": desc,
             "parameters": {"type": "object", "properties": props, "additionalProperties": False}}
            for name, (_, desc, props) in TOOLS.items()]


def call(fd: FlowDeck, name: str, args: dict) -> dict:
    if name not in TOOLS:
        return {"error": f"Unknown tool {name}"}
    fn, _, props = TOOLS[name]
    return fn(fd, **{k: v for k, v in args.items() if k in props})
