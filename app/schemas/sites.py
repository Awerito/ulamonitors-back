from pydantic import BaseModel, Field, field_validator

# Rough bounding box for the southern-Chile aquaculture zone this toy pretends
# to cover; it keeps invented coordinates plausible without pointing anywhere
# in particular.
LAT_MIN, LAT_MAX = -47.0, -40.0
LNG_MIN, LNG_MAX = -76.0, -71.0


def validate_code(v: str) -> str:
    """Site codes are 6 digits with a 9 prefix, so they cannot collide with
    any real industry code."""
    if not v.isdigit() or not v.startswith("9"):
        raise ValueError("code must be digits starting with 9")
    return v


class SiteCreate(BaseModel):
    code: str = Field(min_length=6, max_length=6)
    name: str = Field(min_length=1)
    area: str = Field(min_length=1)
    latitude: float = Field(ge=LAT_MIN, le=LAT_MAX)
    longitude: float = Field(ge=LNG_MIN, le=LNG_MAX)

    _validate_code = field_validator("code")(validate_code)


class SiteUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=6, max_length=6)
    name: str | None = Field(default=None, min_length=1)
    area: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=LAT_MIN, le=LAT_MAX)
    longitude: float | None = Field(default=None, ge=LNG_MIN, le=LNG_MAX)
    active: bool | None = None

    @field_validator("code")
    @classmethod
    def _validate_code(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return validate_code(v)
