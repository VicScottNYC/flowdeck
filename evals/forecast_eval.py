"""Evaluate the capacity forecast against simulated ground truth.

For each seeded day and checkpoint, FlowDeck sees only the messages up to the
checkpoint, forecasts every inpatient unit, then we replay the rest of the day
to get the true occupancy. We compare against a persistence baseline
("occupancy stays the same"), because a forecast that can't beat that isn't useful.

    python evals/forecast_eval.py --seeds 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from flowdeck.demo import seed_demo
from flowdeck.service import FlowDeck

CONFIG = ROOT / "simulator" / "hospital.json"
DAY = datetime(2026, 11, 6)
CHECKPOINTS = ["08:00", "10:00", "12:00", "14:00", "16:00"]
HORIZONS = [4, 8]


def run(seeds: int) -> dict:
    errors = {h: {"model": [], "baseline": []} for h in HORIZONS}
    for seed in range(1, seeds + 1):
        truth = FlowDeck(CONFIG)
        seed_demo(truth, seed=seed, day=DAY, until=None)
        for cp in CHECKPOINTS:
            fd = FlowDeck(CONFIG)
            seed_demo(fd, seed=seed, day=DAY, until=cp)
            for h in HORIZONS:
                target = fd.now + timedelta(hours=h)
                actual = {u["unit"]: u["occupied"] for u in truth.census_at(target).summary()}
                for f in fd.forecast(h):
                    errors[h]["model"].append(abs(f["predicted_occupied"] - actual[f["unit"]]))
                    errors[h]["baseline"].append(abs(f["occupied_now"] - actual[f["unit"]]))
    report = {"seeds": seeds, "checkpoints": CHECKPOINTS, "units_per_checkpoint": 5, "results": {}}
    for h, e in errors.items():
        m = sum(e["model"]) / len(e["model"])
        b = sum(e["baseline"]) / len(e["baseline"])
        report["results"][f"{h}h"] = {"forecasts": len(e["model"]), "mae_beds_model": round(m, 2),
                                      "mae_beds_baseline": round(b, 2),
                                      "improvement_pct": round(100 * (b - m) / b, 1) if b else 0.0}
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--seeds", type=int, default=20)
    p.add_argument("--out", default=str(ROOT / "evals" / "results" / "forecast.json"))
    a = p.parse_args()
    rep = run(a.seeds)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(rep, indent=2))
    print(json.dumps(rep, indent=2))
