from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class AnswerType(StrEnum):
    approved_structured = "APPROVED_STRUCTURED"
    evidence_generated = "EVIDENCE_GENERATED"
    human_review_required = "HUMAN_REVIEW_REQUIRED"


class ApprovedAnswer(BaseModel):
    id: str
    question: str
    answer: str | None
    answer_type: AnswerType
    evidence_ids: list[str] = Field(default_factory=list)
    generation_method: str = "human_approved"
    verified: bool = True
    requires_review: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WorkAuthorizationAssessment(BaseModel):
    matched_answer_id: str | None = None
    answer: str | None = None
    requires_human_review: bool
    reason: str


class ClaimSupportStatus(StrEnum):
    supported = "supported"
    partially_supported = "partially_supported"
    unsupported = "unsupported"
    ambiguous = "ambiguous"


class ClaimValidationRequest(BaseModel):
    generated_claim: str
    supporting_evidence_ids: list[str]


class ClaimValidationResult(BaseModel):
    generated_claim: str
    supporting_evidence_ids: list[str]
    support_status: ClaimSupportStatus
    confidence: float
    reason: str = ""
    action: str
