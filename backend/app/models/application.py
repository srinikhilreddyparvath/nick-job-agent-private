from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ApplicationStatus(StrEnum):
    discovered = "discovered"
    shortlisted = "shortlisted"
    preparing = "preparing"
    ready_for_review = "ready_for_review"
    applied = "applied"
    interview = "interview"
    recruiter_screen = "recruiter_screen"
    final_round = "final_round"
    rejected = "rejected"
    offer = "offer"
    withdrawn = "withdrawn"
    skipped = "skipped"


class ApplicationRead(BaseModel):
    id: int
    job_id: int
    status: ApplicationStatus
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ApplicationEventRead(BaseModel):
    id: int
    application_id: int
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    note: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
