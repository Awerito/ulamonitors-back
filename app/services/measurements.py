from datetime import datetime, timedelta, timezone

from pymongo.asynchronous.database import AsyncDatabase

from app.utils.logger import logger
from app.utils.timezone import utc_to_chile

# The four values every sensor reports, stored in the `measurements`
# collection and aggregated by the overview pipeline.
MEASUREMENT_FIELDS = ("oxygen", "saturation", "temperature", "salinity")

SENSOR_PROJECTION = {"_id": 0}

# A sensor is in no_data after three missed 30-minute transmissions. The
# status is derived at read time because no_data is the ABSENCE of writes:
# nothing would ever write it.
NO_DATA_AFTER = timedelta(minutes=90)


def sensor_status(sensor: dict, *, now: datetime) -> str:
    """Derive the sensor status from its denormalized last reading:
    no_data (nothing in 90 min), out_of_range, or ok."""
    last = sensor["last_reading"]
    if last is None or now - last["at"] > NO_DATA_AFTER:
        return "no_data"
    if not sensor["oxygen_min"] <= last["value"] <= sensor["oxygen_max"]:
        return "out_of_range"
    return "ok"


def serialize_sensor(sensor: dict, *, now: datetime) -> dict:
    """Sensor document -> API shape: derived status, Chile-local timestamps."""
    out = dict(sensor)
    out["status"] = sensor_status(sensor, now=now)
    for field in ("installed_at", "created_at", "updated_at"):
        out[field] = utc_to_chile(out[field])
    if out["last_reading"] is not None:
        out["last_reading"] = {
            "value": out["last_reading"]["value"],
            "at": utc_to_chile(out["last_reading"]["at"]),
        }
    return out


def measurement_doc(sensor: dict, *, values: dict, ts_utc: datetime) -> dict:
    """Build the stored measurement document, denormalizing site_id, depth
    and position so the chart pipeline needs no $lookup."""
    doc = {
        "sensor_id": sensor["id"],
        "site_id": sensor["site_id"],
        "depth": sensor["depth"],
        "position": sensor["position"],
        "timestamp": ts_utc,
        "created_at": datetime.now(timezone.utc),
    }
    for field in MEASUREMENT_FIELDS:
        doc[field] = values[field]
    return doc


def serialize_measurement(doc: dict) -> dict:
    """Measurement document -> API shape: string id, Chile-local timestamps."""
    out = {"id": str(doc["_id"])}
    out.update({k: v for k, v in doc.items() if k != "_id"})
    out["timestamp"] = utc_to_chile(doc["timestamp"])
    out["created_at"] = utc_to_chile(doc["created_at"])
    return out


async def overview(
    db: AsyncDatabase,
    *,
    site_id: int,
    bucket: str,
    days: int,
    depths: list[float] | None = None,
) -> dict:
    """Chart aggregation: avg/min/max per sensor per Chile-local time bucket."""
    coll = db.measurements

    to_utc = datetime.now(timezone.utc)
    from_utc = to_utc - timedelta(days=days)

    match: dict = {
        "site_id": site_id,
        "timestamp": {"$gte": from_utc, "$lte": to_utc},
    }
    if depths:
        match["depth"] = {"$in": depths}

    # Bucket labels are UTC instants of Chile-local boundaries: $dateTrunc with
    # timezone "America/Santiago" (DST-aware). Never replace this with
    # fixed-offset arithmetic ($dateAdd -3/-4): Chile switches between UTC-3
    # and UTC-4 and a fixed offset mislabels every winter bucket, and bucketing
    # in raw UTC aligns "daily" buckets to UTC midnight (20:00-21:00 Chile),
    # not the Chilean day.
    trunc = {
        "$dateTrunc": {
            "date": "$timestamp",
            "unit": bucket,
            "timezone": "America/Santiago",
        }
    }
    group: dict = {
        "_id": {"sensor_id": "$sensor_id", "bucket": trunc},
        "count": {"$sum": 1},
    }
    for f in MEASUREMENT_FIELDS:
        group[f"{f}_avg"] = {"$avg": f"${f}"}
        group[f"{f}_min"] = {"$min": f"${f}"}
        group[f"{f}_max"] = {"$max": f"${f}"}

    pipeline = [{"$match": match}, {"$group": group}, {"$sort": {"_id.bucket": 1}}]
    cursor = await coll.aggregate(pipeline)
    rows = await cursor.to_list()

    points_by_sensor: dict[int, list[dict]] = {}
    for row in rows:
        point = {"bucket": utc_to_chile(row["_id"]["bucket"]), "count": row["count"]}
        for f in MEASUREMENT_FIELDS:
            for stat in ("avg", "min", "max"):
                value = row[f"{f}_{stat}"]
                point[f"{f}_{stat}"] = round(value, 2) if value is not None else None
        points_by_sensor.setdefault(row["_id"]["sensor_id"], []).append(point)

    sensors = await (
        db.sensors.find({"id": {"$in": list(points_by_sensor)}}, SENSOR_PROJECTION)
        .sort("id", 1)
        .to_list()
    )
    data = [
        {
            "sensor_id": sensor["id"],
            "sensor_name": sensor["sensor_name"],
            "depth": sensor["depth"],
            "position": sensor["position"],
            "points": points_by_sensor[sensor["id"]],
        }
        for sensor in sensors
    ]
    logger.info(
        f"[overview] site_id={site_id} bucket={bucket} days={days} "
        f"sensors={len(data)} rows={len(rows)}"
    )
    return {
        "data": data,
        "meta": {
            "siteId": site_id,
            "bucket": bucket,
            "days": days,
            "from": utc_to_chile(from_utc),
            "to": utc_to_chile(to_utc),
        },
    }
