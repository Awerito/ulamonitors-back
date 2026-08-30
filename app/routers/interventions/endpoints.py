from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from pymongo.asynchronous.database import AsyncDatabase

from app.auth import User, current_active_user
from app.database.mongo import get_db
from app.schemas.common import localize, paginated
from app.schemas.interventions import InterventionClose, InterventionCreate

router = APIRouter(tags=["Interventions"])

DbDep = Annotated[AsyncDatabase, Depends(get_db)]

INTERVENTION_PROJECTION = {"_id": 0}

INTERVENTION_TS_FIELDS = ("created_at", "closed_at")


@router.get("/interventions")
async def list_interventions(
    site_id: int | None = None,
    sensor_id: int | None = None,
    status_: Annotated[Literal["open", "closed"] | None, Query(alias="status")] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    *,
    _: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """List interventions, newest first; ?status=open is the pending work."""
    query: dict = {}
    if site_id is not None:
        query["site_id"] = site_id
    if sensor_id is not None:
        query["sensor_id"] = sensor_id
    if status_ is not None:
        query["status"] = status_

    total = await db.interventions.count_documents(query)
    docs = await (
        db.interventions.find(query, INTERVENTION_PROJECTION)
        .sort("created_at", -1)
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )
    data = [localize(d, INTERVENTION_TS_FIELDS) for d in docs]
    return paginated(data, total=total, page=page, page_size=page_size)


@router.post("/interventions", status_code=status.HTTP_201_CREATED)
async def create_intervention(
    body: InterventionCreate,
    current_user: Annotated[User, Security(current_active_user, scopes=["read"])],
    db: DbDep,
) -> dict:
    """Open an intervention. opened_by comes from the token, not the body.
    Requires only the read scope: reporting what you observe is for anyone
    logged in. If the body brings an outcome, the intervention is born
    closed, and that shortcut needs the field scope like PATCH does."""
    if body.outcome is not None and "field" not in current_user.scopes:
        raise HTTPException(
            status_code=403, detail="closing an intervention requires the field scope"
        )
    if await db.sites.find_one({"id": body.site_id}) is None:
        raise HTTPException(status_code=404, detail="site not found")
    if body.sensor_id is not None:
        sensor = await db.sensors.find_one(
            {"id": body.sensor_id, "site_id": body.site_id}
        )
        if sensor is None:
            raise HTTPException(status_code=404, detail="sensor not found in site")
    last = await db.interventions.find_one({}, sort=[("id", -1)])
    now = datetime.now(timezone.utc)
    closed = body.outcome is not None
    doc = {
        "id": (last["id"] if last else 0) + 1,
        "site_id": body.site_id,
        "sensor_id": body.sensor_id,
        "reason": body.reason,
        "status": "closed" if closed else "open",
        "opened_by": current_user.username,
        "created_at": now,
        "outcome": body.outcome,
        "outcome_notes": body.outcome_notes,
        "closed_by": current_user.username if closed else None,
        "closed_at": now if closed else None,
    }
    await db.interventions.insert_one(doc)
    doc.pop("_id", None)
    return localize(doc, INTERVENTION_TS_FIELDS)


@router.patch("/interventions/{intervention_id}")
async def close_intervention(
    intervention_id: int,
    body: InterventionClose,
    current_user: Annotated[User, Security(current_active_user, scopes=["field"])],
    db: DbDep,
) -> dict:
    """Close an intervention with its outcome. closed_by comes from the token.
    Requires the field scope. 409 if it is already closed."""
    intervention = await db.interventions.find_one({"id": intervention_id})
    if intervention is None:
        raise HTTPException(status_code=404, detail="intervention not found")
    if intervention["status"] == "closed":
        raise HTTPException(status_code=409, detail="intervention already closed")
    changes = {
        "status": "closed",
        "outcome": body.outcome,
        "outcome_notes": body.outcome_notes,
        "closed_by": current_user.username,
        "closed_at": datetime.now(timezone.utc),
    }
    await db.interventions.update_one({"id": intervention_id}, {"$set": changes})
    updated = await db.interventions.find_one(
        {"id": intervention_id}, INTERVENTION_PROJECTION
    )
    return localize(updated, INTERVENTION_TS_FIELDS)
