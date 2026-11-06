"""Rule-based operational suggestions.

Deliberately rules, not a language model: every suggestion must be explainable
and reproducible. Each one carries its evidence, and nothing happens until a
named person approves it (see FlowDeck.decide and the audit log).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowdeck.service import FlowDeck

FORECAST_ALERT_PCT = 95.0
BOARDING_ALERT_MIN = 120
BACKLOG_COUNT, BACKLOG_MIN = 3, 120


def generate(fd: FlowDeck) -> list[dict]:
    now = fd.now
    day = now.strftime("%Y%m%d")
    c = fd.census
    out: list[dict] = []
    summary = {u["unit"]: u for u in c.summary()}

    # 1) Units forecast to be (nearly) full within 8 hours
    for f in fd.forecast(8):
        if f["predicted_pct"] >= FORECAST_ALERT_PCT:
            u = summary[f["unit"]]
            ready = [d for d in fd.discharges() if d["unit"] == f["unit"] and d["open_barriers"] == 0]
            out.append({
                "key": f"forecast:{f['unit']}:{day}", "kind": "capacity", "severity": "high",
                "title": f"{f['unit']} projected at {f['predicted_pct']:.0f}% within 8 hours",
                "detail": (f"Prioritize the {len(ready)} discharge-ready patient(s) on {f['unit']}"
                           + (f" and ask EVS to turn its {u['dirty']} dirty bed(s) first." if u["dirty"]
                              else " and confirm transport for each so beds open before evening.")),
                "evidence": {"forecast": f, "dirty_beds": u["dirty"], "ready_discharges": len(ready)},
            })

    # 2) Long ED boarders while matching clean beds exist (a placement gap)
    for b in c.boarding():
        if b["minutes_waiting"] >= BOARDING_ALERT_MIN and b["requested_unit"]:
            clean = summary[b["requested_unit"]]["clean"]
            gap = clean > 0
            out.append({
                "key": f"boarding:{b['visit_number']}", "kind": "boarding",
                "severity": "high" if gap else "medium",
                "title": f"{b['patient_initials']} boarding {b['minutes_waiting'] // 60}h "
                         f"{b['minutes_waiting'] % 60}m in {b['bed_id']} for {b['requested_unit']}",
                "detail": (f"{b['requested_unit']} has {clean} clean bed(s). Assign one now."
                           if gap else f"{b['requested_unit']} has no clean beds. Escalate to the bed huddle."),
                "evidence": {"boarding": b, "clean_beds_in_target": clean},
            })

    # 3) Department backlogs holding up discharges
    by_type: dict[str, list[dict]] = {}
    for bar in fd.open_barriers():
        if bar["minutes_open"] >= BACKLOG_MIN:
            by_type.setdefault(bar["type"], []).append(bar)
    for type_, items in by_type.items():
        if len(items) >= BACKLOG_COUNT:
            dept = items[0]["dept_name"]
            out.append({
                "key": f"backlog:{type_}:{day}:{now.hour // 4}", "kind": "backlog", "severity": "medium",
                "title": f"{dept} backlog: {len(items)} discharge barriers open over 2h",
                "detail": f"Add {dept.lower()} capacity for the next 4 hours or re-prioritize its queue.",
                "evidence": {"type": type_, "count": len(items),
                             "oldest_minutes": max(i["minutes_open"] for i in items),
                             "beds": [i["bed_id"] for i in items]},
            })

    for s in out:
        s["created_at"] = now.isoformat(timespec="seconds")
    return out
