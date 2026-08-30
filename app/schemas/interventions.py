from typing import Literal

from pydantic import BaseModel, Field

Outcome = Literal["back_online", "replaced", "reconfigured", "no_fault_found"]


class InterventionCreate(BaseModel):
    site_id: int
    sensor_id: int | None = None  # null for site-level interventions
    reason: str = Field(min_length=1)
    # When the technician acts on their own initiative the intervention is
    # born closed: outcome (and optionally outcome_notes) comes in the POST.
    outcome: Outcome | None = None
    outcome_notes: str | None = None


class InterventionClose(BaseModel):
    outcome: Outcome
    outcome_notes: str | None = None
