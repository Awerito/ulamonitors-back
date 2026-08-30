from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from pymongo.asynchronous.database import AsyncDatabase

from app.auth import User, current_active_user
from app.database.mongo import get_db
from app.schemas.common import paginated
from app.schemas.sensors import SensorCreate, SensorUpdate
from app.services.measurements import SENSOR_PROJECTION, serialize_sensor

router = APIRouter(tags=["Sensors"])

DbDep = Annotated[AsyncDatabase, Depends(get_db)]


@router.get("/sensors")
async def list_sensors(
    site_id: int | None = None,
    status_: Annotated[
        Literal["ok", "out_of_range", "no_data"] | None, Query(alias="status")
    ] = None,
    position: Literal["jaula", "ponton"] | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    *,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """List sensors with their derived status; ?status= is the dashboard's
    alerts and outages panel."""
    query: dict = {}
    if site_id is not None:
        query["site_id"] = site_id
    if position is not None:
        query["position"] = position

    # status is derived, not stored, so it cannot go into the Mongo query:
    # fetch the filtered set (a few dozen sensors), derive, then paginate.
    sensors = await db.sensors.find(query, SENSOR_PROJECTION).sort("id", 1).to_list()
    now = datetime.now(timezone.utc)
    data = [serialize_sensor(s, now=now) for s in sensors]
    if status_ is not None:
        data = [s for s in data if s["status"] == status_]
    total = len(data)
    skip = (page - 1) * page_size
    return paginated(
        data[skip : skip + page_size], total=total, page=page, page_size=page_size
    )


@router.get("/sensors/{sensor_id}")
async def get_sensor(
    sensor_id: int,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """Sensor detail with its derived status."""
    sensor = await db.sensors.find_one({"id": sensor_id}, SENSOR_PROJECTION)
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    return serialize_sensor(sensor, now=datetime.now(timezone.utc))


@router.post("/sensors", status_code=status.HTTP_201_CREATED)
async def create_sensor(
    body: SensorCreate,
    _: Annotated[User, Security(current_active_user, scopes=["field"])],
    db: DbDep,
) -> dict:
    """Register a sensor on a site. Requires the field scope."""
    if await db.sites.find_one({"id": body.site_id}) is None:
        raise HTTPException(status_code=404, detail="site not found")
    last = await db.sensors.find_one({}, sort=[("id", -1)])
    now = datetime.now(timezone.utc)
    doc = {
        "id": (last["id"] if last else 0) + 1,
        **body.model_dump(),
        "transmitting": True,
        "installed_at": now,
        "last_reading": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.sensors.insert_one(doc)
    doc.pop("_id", None)
    return serialize_sensor(doc, now=now)


@router.patch("/sensors/{sensor_id}")
async def update_sensor(
    sensor_id: int,
    body: SensorUpdate,
    _: Annotated[User, Security(current_active_user, scopes=["field"])],
    db: DbDep,
) -> dict:
    """Configure a sensor: depth, position, range, transmitting. Requires the
    field scope."""
    sensor = await db.sensors.find_one({"id": sensor_id})
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    changes = body.model_dump(exclude_unset=True)
    # The operating range must stay coherent after merging with stored values.
    oxygen_min = changes.get("oxygen_min", sensor["oxygen_min"])
    oxygen_max = changes.get("oxygen_max", sensor["oxygen_max"])
    if oxygen_min >= oxygen_max:
        raise HTTPException(
            status_code=400, detail="oxygen_min must be below oxygen_max"
        )
    changes["updated_at"] = datetime.now(timezone.utc)
    await db.sensors.update_one({"id": sensor_id}, {"$set": changes})
    updated = await db.sensors.find_one({"id": sensor_id}, SENSOR_PROJECTION)
    return serialize_sensor(updated, now=datetime.now(timezone.utc))
