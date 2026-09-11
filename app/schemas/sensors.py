from typing import Literal

from pydantic import BaseModel, Field, model_validator

Depth = Literal[0.5, 5.0, 10.0, 15.0]
Position = Literal["jaula", "ponton"]


class SensorCreate(BaseModel):
    site_id: int
    sensor_name: str = Field(min_length=1)
    position: Position
    depth: Depth
    oxygen_min: float = Field(gt=0)
    oxygen_max: float

    @model_validator(mode="after")
    def _validate_range(self):
        if self.oxygen_min >= self.oxygen_max:
            raise ValueError("oxygen_min must be below oxygen_max")
        return self


class SensorUpdate(BaseModel):
    sensor_name: str | None = Field(default=None, min_length=1)
    position: Position | None = None
    depth: Depth | None = None
    oxygen_min: float | None = Field(default=None, gt=0)
    oxygen_max: float | None = None
    transmitting: bool | None = None
