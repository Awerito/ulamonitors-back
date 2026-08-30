from pymongo.asynchronous.database import AsyncDatabase

from app.services.measurements import KNOWN_MEDITIONS, measurements_collection
from app.utils.logger import logger


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Create every index the API relies on. Idempotent, runs in the lifespan."""
    await db.sites.create_index("id", unique=True)
    await db.sites.create_index("code", unique=True)
    await db.sensors.create_index("id", unique=True)
    await db.sensors.create_index("site_id")
    await db.interventions.create_index("id", unique=True)
    # The list endpoint filters by site or by status and always sorts by
    # created_at descending.
    await db.interventions.create_index([("site_id", 1), ("created_at", -1)])
    await db.interventions.create_index([("status", 1), ("created_at", -1)])
    await db.users.create_index("username", unique=True)
    # One collection per medition: looping KNOWN_MEDITIONS means a new
    # medition gets its measurement indexes for free.
    for medition in KNOWN_MEDITIONS:
        coll = db[measurements_collection(medition)]
        await coll.create_index([("sensor_id", 1), ("timestamp", -1)])
        await coll.create_index([("site_id", 1), ("timestamp", -1)])
    logger.info(f"[indexes] ensured meditions={len(KNOWN_MEDITIONS)}")
