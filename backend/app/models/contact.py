from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class RelationshipStatus(StrEnum):
    verified = "VERIFIED"
    likely_relevant = "LIKELY_RELEVANT"
    unknown = "UNKNOWN"


class ContactEvidence(BaseModel):
    source_url: HttpUrl
    source_type: str
    statement: str


class ContactCandidate(BaseModel):
    name: str
    current_title: str
    company: str
    public_profile_url: HttpUrl
    source_type: str
    source_url: HttpUrl
    team: str | None = None
    domains: list[str] = Field(default_factory=list)
    location: str | None = None
    recruiting_relevance: bool = False
    direct_function_ownership: bool = False
    company_is_small: bool = False
    relationship_status: RelationshipStatus = RelationshipStatus.unknown
    relationship_confidence: float = Field(default=0, ge=0, le=1)
    evidence: list[ContactEvidence] = Field(default_factory=list)


class ContactRead(ContactCandidate):
    contact_id: int
    job_id: int
    role_similarity: float
    team_similarity: float
    domain_similarity: float
    company_match: bool
    seniority_usefulness: float
    location_relevance: float
    relevance_score: float
    relevance_reason: str
    discovered_at: datetime
    last_checked_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ContactList(BaseModel):
    items: list[ContactRead] = Field(default_factory=list)
    status: str = "COMPLETE"
    message: str | None = None
    sources_checked: int = 0
    pages_checked: int = 0
    candidates_discovered: int = 0
    cached: bool = False


class OutreachPreview(BaseModel):
    contact_id: int
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    sent: bool = False
