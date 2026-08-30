# One-time script: fills an empty database with fictional demo data.
# Run with: python -m scripts.seed [--reset]
#
# Every value below is invented. Nothing here comes from a real installation:
# names, codes and coordinates match no existing site.

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings
from app.database.indexes import ensure_indexes
from app.services.measurements import (
    KNOWN_MEDITIONS,
    measurement_doc,
    measurements_collection,
    sensor_status,
)
from app.services.simulation import generate_reading, saturation_for
from app.utils.logger import logger

BATCH_SIZE = 5000
HISTORY_DAYS = 30
STEP = timedelta(minutes=30)
# The history tells four stories, spread across the 32 sensors, so no two
# charts look alike (the README lists which sensor shows which):
# - Ongoing outage: readings stop some days before now and never resume, at a
#   different height of the period per sensor. transmitting=False keeps the
#   scheduler from resurrecting them, and the stale last_reading derives
#   no_data from the very first boot.
# - Gap and recovery: a hole in the middle of the series, then transmission
#   resumes and runs up to now. This is what a repaired sensor looks like.
# - Late install: installed_at falls inside the 30-day window, so the line
#   starts mid-chart.
# - Every other sensor is healthy: a full continuous series as contrast.
OUTAGE_STOP_DAYS = {7: 3.0, 13: 6.0, 22: 0.5}  # sensor id -> days before now
GAP_WINDOWS = {4: (12.0, 10.0), 18: (6.0, 5.5)}  # sensor id -> days-ago window
LATE_INSTALL_DAYS = {10: 12.0, 27: 8.0}  # sensor id -> installed days ago

# Every value below is fictional: invented site names, codes with a 9 prefix
# so they cannot collide with anything real, and coordinates randomized inside
# a southern-Chile bounding box pointing at no existing installation.
SITE_NAMES = [
    "Canal Espejo",
    "Punta Neblina",
    "Isla Cormorán",
    "Bahía Brumas",
    "Seno Escondido",
    "Estero Relámpago",
    "Islote Garza",
    "Fiordo Cristal",
]
AREAS = ["Zona Norte", "Zona Centro", "Zona Sur"]

# Two pontón depths per site, cycling across the canonical depths.
PONTON_DEPTHS = [(0.5, 15.0), (5.0, 10.0), (0.5, 10.0), (5.0, 15.0)]

INTERVENTION_OUTCOMES = ["back_online", "replaced", "reconfigured", "no_fault_found"]
INTERVENTION_REASONS = [
    "Intermittent readings reported by the dashboard.",
    "Oxygen values drifting against the field probe.",
    "Antenna misalignment suspected after a storm.",
    "Battery voltage dropping in telemetry.",
    "Scheduled maintenance visit.",
]
INTERVENTION_OUTCOME_NOTES = [
    "Cleaned the optical window and verified readings.",
    "Replaced the battery pack.",
    "Recalibrated against the field probe.",
    "Realigned the satellite antenna.",
    "Updated the logger firmware.",
]
# Reasons for the open interventions flagged on the sensors the seed leaves
# in trouble, keyed by derived status.
OPEN_REASONS = {
    "no_data": "Not transmitting since the satellite link dropped.",
    "out_of_range": "Oxygen reading outside the operating range.",
}

async def seed(db: AsyncDatabase, *, reset: bool = False) -> None:
    """Populate the database with sites, sensors, interventions and 30 days
    of simulated oxygen history.

    Users are NOT touched. They are created through POST /users and must
    survive --reset, so the accounts handed out to the class are not wiped
    every night.

    Idempotent: if sites already exist it logs and returns. Deterministic
    (random.Random(42)) so every group gets the same data.
    """
    if reset:
        for name in (
            "sites",
            "sensors",
            "interventions",
            *[measurements_collection(m) for m in KNOWN_MEDITIONS],
        ):
            await db.drop_collection(name)
        logger.info("[seed] collections dropped")

    if await db.sites.count_documents({}) > 0:
        logger.info("[seed] already seeded")
        return

    rng = random.Random(42)
    now = datetime.now(timezone.utc)

    # Eight sites, the last one inactive so the filters show something.
    sites = []
    used_codes: set[str] = set()
    for i, name in enumerate(SITE_NAMES, start=1):
        code = f"9{rng.randint(10000, 99999)}"
        while code in used_codes:
            code = f"9{rng.randint(10000, 99999)}"
        used_codes.add(code)
        sites.append(
            {
                "id": i,
                "code": code,
                "name": name,
                "area": AREAS[(i - 1) % len(AREAS)],
                "latitude": round(rng.uniform(-45.5, -42.0), 5),
                "longitude": round(rng.uniform(-74.0, -72.5), 5),
                "active": i != len(SITE_NAMES),
                "created_at": now,
                "updated_at": now,
            }
        )

    # Four oxygen sensors per site: two jaula at 5 and 10 m, two pontón.
    sensors = []
    sensor_id = 0
    for site in sites:
        ponton_depths = PONTON_DEPTHS[(site["id"] - 1) % len(PONTON_DEPTHS)]
        jaula_number = 100 + site["id"]
        layout = [
            ("jaula", 5.0, f"Jaula {jaula_number} 5m"),
            ("jaula", 10.0, f"Jaula {jaula_number} 10m"),
            *[
                (
                    "ponton",
                    d,
                    f"Ponton {site['id']} {int(d) if d.is_integer() else d}m",
                )
                for d in ponton_depths
            ],
        ]
        for position, depth, name in layout:
            sensor_id += 1
            sensors.append(
                {
                    "id": sensor_id,
                    "site_id": site["id"],
                    "medition": "oxygen",
                    "sensor_name": name,
                    "position": position,
                    "depth": depth,
                    "oxygen_min": round(rng.uniform(4.0, 5.0), 1),
                    "oxygen_max": round(rng.uniform(12.0, 14.0), 1),
                    "transmitting": True,
                    "installed_at": now - timedelta(days=rng.uniform(60, 400)),
                    "last_reading": None,
                    "created_at": now,
                    "updated_at": now,
                }
            )
    # Apply the stories that live on the sensor document itself: outage
    # sensors stop transmitting, late installs get a recent installed_at.
    for sid in OUTAGE_STOP_DAYS:
        sensors[sid - 1]["transmitting"] = False
    for sid, days in LATE_INSTALL_DAYS.items():
        sensors[sid - 1]["installed_at"] = now - timedelta(days=days)

    await db.sites.insert_many(sites)
    await db.sensors.insert_many(sensors)

    # 30 days of history, one reading every 30 minutes, shaped per sensor by
    # the story tables above. Hypoxia excursions come from the deterministic
    # schedule inside generate_reading, so out-of-range sensors show the
    # excursion across their whole series, not only in the last value.
    start = now - timedelta(days=HISTORY_DAYS)
    timestamps = [start + STEP * i for i in range(HISTORY_DAYS * 48)]
    timestamps[-1] = now  # the newest reading is exactly "now"

    batch: list[dict] = []
    last_reading: dict[int, dict] = {}
    for sensor in sensors:
        stop_days = OUTAGE_STOP_DAYS.get(sensor["id"])
        stop_at = now - timedelta(days=stop_days) if stop_days else None
        gap = GAP_WINDOWS.get(sensor["id"])
        if gap:
            gap_from = now - timedelta(days=gap[0])
            gap_to = now - timedelta(days=gap[1])
        for ts in timestamps:
            if ts < sensor["installed_at"]:
                continue  # late install: nothing before the sensor exists
            if stop_at and ts > stop_at:
                break  # ongoing outage: the series ends here
            if gap and gap_from < ts < gap_to:
                continue  # gap and recovery: skip the hole, resume after
            values = generate_reading(sensor, ts, rng)
            batch.append(measurement_doc(sensor, values=values, ts_utc=ts))
            last_reading[sensor["id"]] = {"value": values["oxygen"], "at": ts}
            if len(batch) >= BATCH_SIZE:
                await db[measurements_collection("oxygen")].insert_many(batch)
                batch = []
    if batch:
        await db[measurements_collection("oxygen")].insert_many(batch)

    for sensor in sensors:
        sensor["last_reading"] = last_reading[sensor["id"]]
        await db.sensors.update_one(
            {"id": sensor["id"]},
            {"$set": {"last_reading": sensor["last_reading"]}},
        )

    # A month of closed interventions so the list has history, then one open
    # intervention per sensor currently in no_data or out_of_range, flagged
    # from the dashboard, so the pending-work view makes sense on first boot.
    interventions = []
    for i in range(1, 11):
        site = rng.choice(sites)
        site_sensors = [s for s in sensors if s["site_id"] == site["id"]]
        sensor = rng.choice(site_sensors) if rng.random() < 0.7 else None
        opened_at = now - timedelta(days=rng.uniform(3, HISTORY_DAYS))
        interventions.append(
            {
                "id": i,
                "site_id": site["id"],
                "sensor_id": sensor["id"] if sensor else None,
                "reason": rng.choice(INTERVENTION_REASONS),
                "status": "closed",
                "opened_by": rng.choice(["dashboard", "tech"]),
                "created_at": opened_at,
                "outcome": rng.choice(INTERVENTION_OUTCOMES),
                "outcome_notes": rng.choice(INTERVENTION_OUTCOME_NOTES),
                "closed_by": "tech",
                "closed_at": opened_at + timedelta(hours=rng.uniform(4, 48)),
            }
        )
    for sensor in sensors:
        derived = sensor_status(sensor, now=now)
        if derived == "ok":
            continue
        interventions.append(
            {
                "id": len(interventions) + 1,
                "site_id": sensor["site_id"],
                "sensor_id": sensor["id"],
                "reason": OPEN_REASONS[derived],
                "status": "open",
                "opened_by": "dashboard",
                "created_at": now - timedelta(hours=rng.uniform(1, 24)),
                "outcome": None,
                "outcome_notes": None,
                "closed_by": None,
                "closed_at": None,
            }
        )
    await db.interventions.insert_many(interventions)

    logger.info(
        f"[seed] sites={len(sites)} sensors={len(sensors)} "
        f"interventions={len(interventions)}"
    )
    for medition in KNOWN_MEDITIONS:
        count = await db[measurements_collection(medition)].count_documents({})
        logger.info(
            f"[seed] collection={measurements_collection(medition)} docs={count}"
        )
    by_status: dict[str, list[str]] = {}
    for sensor in sensors:
        by_status.setdefault(sensor_status(sensor, now=now), []).append(
            sensor["sensor_name"]
        )
    logger.info(f"[seed] no_data={by_status.get('no_data', [])}")
    logger.info(f"[seed] out_of_range={by_status.get('out_of_range', [])}")


async def main(reset: bool) -> None:
    """Open a client, ensure indexes, seed, close."""
    client: AsyncMongoClient = AsyncMongoClient(settings.mongo_uri, tz_aware=True)
    try:
        db = client.get_database()
        # Indexes after seeding: --reset drops the collections, which would
        # drop indexes created beforehand.
        await seed(db, reset=reset)
        await ensure_indexes(db)
    finally:
        await client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the ulamonitors database.")
    parser.add_argument(
        "--reset", action="store_true", help="drop the collections before seeding"
    )
    asyncio.run(main(parser.parse_args().reset))
