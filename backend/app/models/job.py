from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from app.models.role_family import RoleFamily
from app.models.opportunity import OpportunityScore


class RemoteType(StrEnum):
    remote = "remote"
    hybrid = "hybrid"
    onsite = "onsite"
    unspecified = "unspecified"


class Recommendation(StrEnum):
    exceptional = "exceptional"
    strong = "strong"
    possible = "possible"
    weak = "weak"
    skip = "skip"


class JobBase(BaseModel):
    external_id: str
    source: str
    company: str
    title: str
    location: str | None = None
    remote_type: RemoteType = RemoteType.unspecified
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str | None = None
    description: str = ""
    requirements: list[str] = Field(default_factory=list)
    preferred_qualifications: list[str] = Field(default_factory=list)
    apply_url: HttpUrl
    source_url: HttpUrl
    posted_at: datetime | None = None
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JobCreate(JobBase):
    pass


class ComponentScore(BaseModel):
    score: float = Field(ge=0, le=100)
    weight: float = Field(gt=0, le=1)
    explanation: str


class Job(JobBase):
    id: int | None = None
    fit_score: float | None = None
    fit_explanation: str | None = None
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    recommendation: Recommendation | None = None
    application_status: str | None = None
    component_scores: dict[str, ComponentScore] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    human_label: str | None = None
    human_notes: str | None = None
    role_family: RoleFamily = RoleFamily.unknown
    role_family_confidence: float = 0
    role_family_reasons: list[str] = Field(default_factory=list)
    classification_method: str = "deterministic_rules"
    deterministic_family: RoleFamily | None = None
    deterministic_confidence: float | None = None
    semantic_family: RoleFamily | None = None
    semantic_confidence: float | None = None
    final_family: RoleFamily | None = None
    classification_resolution_method: str | None = None
    family_fit_score: float | None = None
    family_component_scores: dict[str, dict] = Field(default_factory=dict)
    matched_evidence_ids: list[str] = Field(default_factory=list)
    career_transition_flag: bool = False
    career_transition_notes: str | None = None
    raw_company: str | None = None
    canonical_company: str | None = None
    normalized_location: str | None = None
    alternate_sources: list[dict] = Field(default_factory=list)
    opportunity_score: OpportunityScore | None = None
    semantic_fit_score: float | None = None
    semantic_fit_confidence: float | None = None
    semantic_analysis_status: str = "NOT_ANALYZED"
    semantic_provider: str | None = None
    semantic_model: str | None = None
    semantic_estimated_cost: float = 0

    model_config = ConfigDict(from_attributes=True)


class ScoreResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    component_scores: dict[str, ComponentScore]
    strengths: list[str]
    gaps: list[str]
    matched_skills: list[str]
    missing_skills: list[str]
    reasoning_summary: str
    recommendation: Recommendation


class ScanRequest(BaseModel):
    connector: str
    company: str
    identifier: str


class ScanResult(BaseModel):
    connector: str
    discovered: int
    created: int
    duplicates: int
    filtered_out: int
    job_ids: list[int]


class JobList(BaseModel):
    items: list[Job]
    total: int
    counts: dict[str, int]
