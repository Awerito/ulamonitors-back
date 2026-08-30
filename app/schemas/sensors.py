from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.measurements import CANONICAL_DEPTHS, KNOWN_MEDITIONS


class SensorCreate(BaseModel):
    site_id: int
    medition: str = "oxygen"
    sensor_name: str = Field(min_length=1)
    position: Literal["jaula", "ponton"]
    depth: float
    oxygen_min: float = Field(gt=0)
    oxygen_max: float

    @field_validator("medition")
    @classmethod
    def _validate_medition(cls, v: str) -> str:
        if v not in KNOWN_MEDITIONS:
            raise ValueError(f"unknown medition: {v}")
        return v

    @field_validator("depth")
    @classmethod
    def _validate_depth(cls, v: float) -> float:
        if v not in CANONICAL_DEPTHS:
            raise ValueError(f"depth must be one of {list(CANONICAL_DEPTHS)}")
        return v

    @model_validator(mode="after")
    def _validate_range(self):
        if self.oxygen_min >= self.oxygen_max:
            raise ValueError("oxygen_min must be below oxygen_max")
        return self


class SensorUpdate(BaseModel):
    sensor_name: str | None = Field(default=None, min_length=1)
    position: Literal["jaula", "ponton"] | None = None
    depth: float | None = None
    oxygen_min: float | None = Field(default=None, gt=0)
    oxygen_max: float | None = None
    transmitting: bool | None = None

    @field_validator("depth")
    @classmethod
    def _validate_depth(cls, v: float | None) -> float | None:
        if v is not None and v not in CANONICAL_DEPTHS:
            raise ValueError(f"depth must be one of {list(CANONICAL_DEPTHS)}")
        return v
