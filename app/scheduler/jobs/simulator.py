import random
from datetime import datetime, timezone

from app.database.mongo import get_db
from app.services.measurements import measurement_doc
from app.services.simulation import generate_reading
from app.utils.logger import logger

_rng = random.Random()


async def simulate_readings() -> None:
    """Insert one simulated reading per transmitting sensor.

    This job plays the role of the sensors themselves — the vendor's loggers
    push data, nobody types it. Sensors with transmitting=false get nothing,
    so their last_reading ages and the derived status shows the outage until
    a technician repairs them through the mobile app.
    """
    db = get_db()
    sensors = await db.sensors.find({"transmitting": True}, {"_id": 0}).to_list()
    now = datetime.now(timezone.utc)
    for sensor in sensors:
        values = generate_reading(sensor, now, _rng)
        await db.measurements.insert_one(
            measurement_doc(sensor, values=values, ts_utc=now)
        )
        await db.sensors.update_one(
            {"id": sensor["id"]},
            {"$set": {"last_reading": {"value": values["oxygen"], "at": now}}},
        )
    logger.info(f"[simulator] sensors={len(sensors)}")
