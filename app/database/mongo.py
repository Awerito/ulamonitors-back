from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.config import settings
from app.utils.logger import logger

# Ported from the Motor-based template (Motor reached EOL in 2026). Three
# behavioural differences with pymongo's async client that a mechanical port
# gets wrong:
#   - `client.close()` is now a coroutine and must be awaited.
#   - `collection.aggregate(pipeline)` must be awaited to get the cursor.
#   - `cursor.to_list()` no longer requires a length argument.

_client: AsyncMongoClient | None = None


async def connect() -> AsyncDatabase:
    """Open the MongoDB client, ping the server, and return the database."""
    global _client
    # tz_aware=True so every datetime read back is aware UTC; the timezone
    # contract (app/utils/timezone.py) then converts explicitly at the edges.
    _client = AsyncMongoClient(settings.mongo_uri, maxIdleTimeMS=60000, tz_aware=True)
    db = _client.get_database()
    await db.command("ping")
    info = await _client.server_info()
    logger.info(f"[mongo] connected version={info.get('version', 'unknown')}")
    return db


async def disconnect() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


def get_db() -> AsyncDatabase:
    """FastAPI dependency that returns the database from the singleton client."""
    if _client is None:
        raise RuntimeError("MongoDB client not initialized. Did lifespan run?")
    return _client.get_database()
