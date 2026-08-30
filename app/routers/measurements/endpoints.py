from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from pymongo.asynchronous.database import AsyncDatabase

from app.auth import User, current_active_user
from app.database.mongo import get_db
from app.schemas.common import paginated
from app.services.measurements import (
    measurements_collection,
    overview,
    serialize_measurement,
)
from app.utils.timezone import chile_to_utc

router = APIRouter(tags=["Measurements"])

DbDep = Annotated[AsyncDatabase, Depends(get_db)]


@router.get("/measurements")
async def list_measurements(
    sensor_id: int | None = None,
    site_id: int | None = None,
    medition: str = "oxygen",
    from_: Annotated[datetime | None, Query(alias="from")] = None,
    to: datetime | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    *,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """Raw measurements for a sensor or a site, newest first."""
    if sensor_id is None and site_id is None:
        raise HTTPException(status_code=400, detail="sensor_id or site_id is required")
    try:
        coll = db[measurements_collection(medition)]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    query: dict = {}
    if sensor_id is not None:
        query["sensor_id"] = sensor_id
    if site_id is not None:
        query["site_id"] = site_id
    time_filter: dict = {}
    if from_ is not None:
        time_filter["$gte"] = chile_to_utc(from_)
    if to is not None:
        time_filter["$lte"] = chile_to_utc(to)
    if time_filter:
        query["timestamp"] = time_filter

    total = await coll.count_documents(query)
    docs = await (
        coll.find(query)
        .sort("timestamp", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )
    data = [serialize_measurement(d) for d in docs]
    return paginated(data, total=total, page=page, page_size=page_size)


@router.get("/measurements/overview")
async def measurements_overview(
    site_id: int,
    medition: str = "oxygen",
    bucket: Literal["hour", "day"] = "hour",
    days: int = Query(7, ge=1, le=365),
    depths: str | None = None,
    *,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """Aggregated chart data per sensor and Chile-local time bucket.

    `depths` is a comma-separated list, e.g. depths=5,10.
    """
    depth_list = None
    if depths:
        try:
            depth_list = [float(d) for d in depths.split(",") if d.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="depths must be numbers")
    try:
        return await overview(
            db,
            site_id=site_id,
            medition=medition,
            bucket=bucket,
            days=days,
            depths=depth_list,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
