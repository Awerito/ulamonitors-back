import math
import random
from datetime import datetime

from app.utils.timezone import utc_to_chile

# Hypoxia excursions are DETERMINISTIC in (sensor_id, timestamp): each sensor
# dips below its operating minimum for 7.2 hours every 72, with per-sensor
# phases spaced 2.4 h apart, so the excursion window always covers three
# consecutive sensor phases. The seed's history and the live scheduler share
# this schedule, so a sensor out of range at boot stays out of range across
# ticks until its excursion ends — and at any instant 2-3 sensors are in
# excursion, which keeps the dashboard interesting.
EXCURSION_PERIOD_H = 72.0
EXCURSION_DURATION_H = 7.2
EXCURSION_SPACING_H = 2.4


def saturation_for(oxygen: float, temperature: float) -> float:
    """Percent saturation from oxygen (mg/L) and temperature (C).

    Linear solubility approximation, good enough to make saturation move
    inversely with temperature — a teaching approximation, not the Weiss
    equation real systems use.
    """
    solubility = 14.6 - 0.32 * temperature  # ~14.6 mg/L at 0 C, ~6.6 at 25 C
    return max(0.0, min(200.0, oxygen / solubility * 100))


def generate_reading(sensor: dict, ts: datetime, rng: random.Random) -> dict:
    """One synthetic reading for a sensor at a UTC instant.

    Shared by the seed and the scheduler so the historical series and the
    live one are continuous.
    """
    local = utc_to_chile(ts)
    hour = local.hour + local.minute / 60
    day_of_year = local.timetuple().tm_yday

    # The daily oxygen cycle peaks around 17:00 CHILE LOCAL (photosynthesis),
    # so the phase must come from the Chile clock, not from UTC.
    daily = math.cos(2 * math.pi * (hour - 17) / 24)
    # Southern hemisphere: warmest around mid January (day ~15).
    seasonal = math.cos(2 * math.pi * (day_of_year - 15) / 365)

    depth = sensor["depth"]
    temperature = 11.5 + 3.0 * seasonal - 0.06 * depth + 0.5 * daily + rng.gauss(0, 0.2)
    oxygen = 9.0 - 0.12 * depth + 0.8 * daily + rng.gauss(0, 0.3)
    salinity = (
        31.5 + 1.2 * math.sin(2 * math.pi * day_of_year / 90) + rng.gauss(0, 0.15)
    )

    hours = ts.timestamp() / 3600
    phase = (hours + sensor["id"] * EXCURSION_SPACING_H) % EXCURSION_PERIOD_H
    if phase < EXCURSION_DURATION_H:
        oxygen = max(0.2, sensor["oxygen_min"] - 1.0 + rng.gauss(0, 0.3))

    saturation = saturation_for(oxygen, temperature) + rng.gauss(0, 1.0)

    return {
        "oxygen": round(max(0.0, min(25.0, oxygen)), 2),
        "saturation": round(max(0.0, min(200.0, saturation)), 2),
        "temperature": round(max(-5.0, min(35.0, temperature)), 2),
        "salinity": round(max(0.0, min(45.0, salinity)), 2),
    }
