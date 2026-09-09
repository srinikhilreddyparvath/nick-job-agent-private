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
    hired = "hired"
    no_response = "no_response"
    skipped = "skipped"
    ready_to_fill="READY_TO_FILL";filling="FILLING";filled="FILLED";needs_review="NEEDS_REVIEW";ready_to_submit="READY_TO_SUBMIT";submitting="SUBMITTING";submitted="SUBMITTED";submission_unverified="SUBMISSION_UNVERIFIED";submission_failed="SUBMISSION_FAILED";submission_timeout="SUBMISSION_TIMEOUT";blocked="BLOCKED";failed="FAILED"


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
