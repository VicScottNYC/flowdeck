"""Capacity forecast: transparent, explainable, and evaluated (see evals/).

Predicted occupied beds for a unit, ``h`` hours ahead =
    occupied now
  + patients boarding in the ED for this unit (they will take a bed)
  + expected new admit decisions  (recent rate x h)
  - expected discharges           (sum of per-patient probabilities)

Each expected discharge gets a probability of happening inside the window,
using the hospital's discharge-time curve, conditioned on "hasn't happened yet".
Open barriers lower that probability. No black box: every term is returned so
the UI and the AI assistant can explain the number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# Discharge-time curve (hours of day). In production this is fitted from history;
# here it matches what the simulator's hospital does: 09:00–19:00, peak at 14:00.
DISCHARGE_WINDOW = (9.0, 19.0, 14.0)
OPEN_BARRIER_FACTOR = 0.45


def _tri_cdf(x: float, a: float, b: float, c: float) -> float:
    if x <= a:
        return 0.0
    if x >= b:
        return 1.0
    if x <= c:
        return (x - a) ** 2 / ((b - a) * (c - a))
    return 1 - (b - x) ** 2 / ((b - a) * (b - c))


def discharge_probability(now: datetime, hours: float, open_barriers: int) -> float:
    a, b, c = DISCHARGE_WINDOW
    t = now.hour + now.minute / 60
    end = min(t + hours, 24.0)
    done = _tri_cdf(t, a, b, c)
    if done >= 1.0:
        return 0.0
    p = (_tri_cdf(end, a, b, c) - done) / (1 - done)
    return p * (OPEN_BARRIER_FACTOR if open_barriers else 1.0)


@dataclass
class UnitForecast:
    unit: str
    hours: int
    total: int
    occupied_now: int
    boarding_inbound: int
    expected_admits: float
    expected_discharges: float
    predicted_occupied: int
    predicted_pct: float
    at: str

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def forecast_unit(unit: str, total: int, occupied_now: int, boarding_inbound: int, admit_rate_per_hr: float,
                  discharge_candidates: list[int], now: datetime, hours: int) -> UnitForecast:
    """``discharge_candidates`` = open-barrier counts, one per expected discharge still in a bed."""
    exp_dc = sum(discharge_probability(now, hours, n) for n in discharge_candidates)
    exp_adm = admit_rate_per_hr * hours
    raw = occupied_now + boarding_inbound + exp_adm - exp_dc
    pred = max(0, min(total, round(raw)))
    return UnitForecast(unit, hours, total, occupied_now, boarding_inbound, round(exp_adm, 1), round(exp_dc, 1),
                        pred, round(100 * pred / total, 1), (now + timedelta(hours=hours)).isoformat())
