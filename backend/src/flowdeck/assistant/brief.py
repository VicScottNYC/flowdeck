"""Bed huddle brief: a one-page, structured summary for the daily capacity huddle."""

from __future__ import annotations

from flowdeck.service import FlowDeck


def huddle_brief(fd: FlowDeck) -> dict:
    o = fd.overview()
    k = o["kpis"]
    fc8 = sorted(fd.forecast(8), key=lambda f: -f["predicted_pct"])
    barriers = fd.open_barriers()
    by_dept: dict[str, int] = {}
    for b in barriers:
        by_dept[b["dept_name"]] = by_dept.get(b["dept_name"], 0) + 1
    risks = [f for f in fc8 if f["predicted_pct"] >= 90]
    headline = (f"{len(risks)} unit(s) projected at or above 90% within 8 hours"
                if risks else "No unit projected above 90% in the next 8 hours")
    return {
        "as_of": o["as_of"],
        "headline": headline,
        "capacity": {"inpatient_occupancy_pct": k["inpatient_occupancy_pct"], "clean_beds": k["clean_beds"],
                     "dirty_beds": k["dirty_beds"], "ed_boarding": k["ed_boarding"]},
        "discharges": {"remaining": k["expected_discharges_remaining"], "ready": k["discharges_ready"],
                       "blocked": k["expected_discharges_remaining"] - k["discharges_ready"]},
        "forecast_risks": [{"unit": f["unit"], "predicted_pct": f["predicted_pct"], "at": f["at"]} for f in risks],
        "top_barriers": [{k2: b[k2] for k2 in ("bed_id", "patient_initials", "dept_name", "note", "minutes_open")}
                         for b in barriers[:5]],
        "barriers_by_department": dict(sorted(by_dept.items(), key=lambda kv: -kv[1])),
        "boarding": fd.census.boarding()[:5],
    }
