import re
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from pymongo.asynchronous.database import AsyncDatabase

from app.auth import User, current_active_user
from app.database.mongo import get_db
from app.schemas.common import localize, paginated
from app.schemas.sites import SiteCreate, SiteUpdate
from app.services.measurements import SENSOR_PROJECTION, serialize_sensor

router = APIRouter(tags=["Sites"])

DbDep = Annotated[AsyncDatabase, Depends(get_db)]

SITE_PROJECTION = {"_id": 0}

SITE_TS_FIELDS = ("created_at", "updated_at")


@router.get("/sites")
async def list_sites(
    q: str | None = None,
    area: str | None = None,
    active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    *,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """List sites with optional name search and area/active filters."""
    query: dict = {}
    if q:
        # Escape the raw parameter: it is a literal search, and regex
        # metacharacters like ( * [ would otherwise make Mongo reject the
        # query with a 500.
        query["name"] = {"$regex": re.escape(q), "$options": "i"}
    if area:
        query["area"] = area
    if active is not None:
        query["active"] = active

    total = await db.sites.count_documents(query)
    sites = await (
        db.sites.find(query, SITE_PROJECTION)
        .sort("name", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )
    data = [localize(s, SITE_TS_FIELDS) for s in sites]
    return paginated(data, total=total, page=page, page_size=page_size)


@router.get("/sites/{site_id}")
async def get_site(
    site_id: int,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """Site detail with its sensors, each carrying its derived status."""
    site = await db.sites.find_one({"id": site_id}, SITE_PROJECTION)
    if site is None:
        raise HTTPException(status_code=404, detail="site not found")
    sensors = await (
        db.sensors.find({"site_id": site_id}, SENSOR_PROJECTION).sort("id", 1).to_list()
    )
    now = datetime.now(timezone.utc)
    out = localize(site, SITE_TS_FIELDS)
    out["sensors"] = [serialize_sensor(s, now=now) for s in sensors]
    return out


@router.post("/sites", status_code=status.HTTP_201_CREATED)
async def create_site(
    body: SiteCreate,
    _: Annotated[User, Security(current_active_user, scopes=["field"])],
    db: DbDep,
) -> dict:
    """Register a site. Requires the field scope."""
    if await db.sites.find_one({"code": body.code}):
        raise HTTPException(status_code=409, detail="code already exists")
    last = await db.sites.find_one({}, sort=[("id", -1)])
    now = datetime.now(timezone.utc)
    doc = {
        "id": (last["id"] if last else 0) + 1,
        **body.model_dump(),
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    await db.sites.insert_one(doc)
    doc.pop("_id", None)
    return localize(doc, SITE_TS_FIELDS)


@router.patch("/sites/{site_id}")
async def update_site(
    site_id: int,
    body: SiteUpdate,
    _: Annotated[User, Security(current_active_user, scopes=["field"])],
    db: DbDep,
) -> dict:
    """Partially update a site. Requires the field scope."""
    site = await db.sites.find_one({"id": site_id})
    if site is None:
        raise HTTPException(status_code=404, detail="site not found")
    changes = body.model_dump(exclude_unset=True)
    if "code" in changes and changes["code"] != site["code"]:
        if await db.sites.find_one({"code": changes["code"]}):
            raise HTTPException(status_code=409, detail="code already exists")
    changes["updated_at"] = datetime.now(timezone.utc)
    await db.sites.update_one({"id": site_id}, {"$set": changes})
    updated = await db.sites.find_one({"id": site_id}, SITE_PROJECTION)
    return localize(updated, SITE_TS_FIELDS)
