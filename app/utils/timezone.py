from datetime import datetime
from zoneinfo import ZoneInfo

# Timezone contract — read this before touching any endpoint or service that
# handles timestamps:
#
# 1. The database is the source of truth and stores EVERY timestamp in UTC.
#    Never rewrite stored data to local time.
#
# 2. Every HTTP endpoint speaks Chile local time (America/Santiago, DST-aware:
#    UTC-3 in summer, UTC-4 in winter), so at the service boundary you MUST
#    convert on both sides: incoming timestamp query params are Chile local
#    -> chile_to_utc() BEFORE building the DB filter; outgoing timestamp
#    fields are UTC as stored -> utc_to_chile() BEFORE the response. Doing
#    only one half (or neither) silently shifts results by the Chile offset
#    (3-4 h), so charts and time filters look plausible but are wrong by
#    hours — easy to miss because nothing errors. If you add an endpoint
#    that reads or writes a timestamp, wire both conversions and grep this
#    module's callers to stay consistent.
#
# 3. Calendar buckets (daily/hourly charts) must be built in Chile time, not
#    UTC — see the $dateTrunc pipeline in app/services/measurements.py.
CHILE_TZ = ZoneInfo("America/Santiago")
UTC_TZ = ZoneInfo("UTC")


def chile_to_utc(dt: datetime) -> datetime:
    """Chile-local datetime (naive is assumed Chile) -> aware UTC, for DB
    query bounds. Already-aware datetimes are just normalized to UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CHILE_TZ)
    return dt.astimezone(UTC_TZ)


def utc_to_chile(dt: datetime) -> datetime:
    """UTC datetime as stored in the DB (naive is assumed UTC) -> naive
    Chile-local, for API responses."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(CHILE_TZ).replace(tzinfo=None)
