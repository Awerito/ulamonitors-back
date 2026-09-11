from pydantic import BaseModel, Field

# Rough bounding box for the southern-Chile aquaculture zone this toy pretends
# to cover; it keeps invented coordinates plausible without pointing anywhere
# in particular.
LAT_MIN, LAT_MAX = -47.0, -40.0
LNG_MIN, LNG_MAX = -76.0, -71.0

# Site codes are 6 digits with a 9 prefix, so they cannot collide with any
# real industry code.
CODE_PATTERN = r"^9\d{5}$"


class SiteCreate(BaseModel):
    code: str = Field(pattern=CODE_PATTERN)
    name: str = Field(min_length=1)
    area: str = Field(min_length=1)
    latitude: float = Field(ge=LAT_MIN, le=LAT_MAX)
    longitude: float = Field(ge=LNG_MIN, le=LNG_MAX)


class SiteUpdate(BaseModel):
    code: str | None = Field(default=None, pattern=CODE_PATTERN)
    name: str | None = Field(default=None, min_length=1)
    area: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=LAT_MIN, le=LAT_MAX)
    longitude: float | None = Field(default=None, ge=LNG_MIN, le=LNG_MAX)
    active: bool | None = None
