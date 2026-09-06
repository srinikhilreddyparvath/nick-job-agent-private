from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, HttpUrl, computed_field


class Evidence(BaseModel):
    source: str
    reference: str | None = None
    verified: bool = False
    notes: str | None = None


class ProfileItem(BaseModel):
    value: str
    details: dict[str, Any] = Field(default_factory=dict)
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class Identity(BaseModel):
    legal_first_name: str | None = None
    legal_last_name: str | None = None
    preferred_first_name: str | None = None
    preferred_professional_name: str | None = None
    display_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    portfolio_url: HttpUrl | None = None
    linkedin_url: HttpUrl | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)

    @computed_field
    @property
    def legal_name(self) -> str | None:
        parts = [self.legal_first_name, self.legal_last_name]
        value = " ".join(part for part in parts if part)
        return value or None

    @computed_field
    @property
    def name(self) -> str | None:
        return self.display_name or self.preferred_professional_name


class EvidenceRecord(BaseModel):
    id: str
    category: str
    sub_category: str
    statement: str
    source: str
    source_reference: str
    company: str | None = None
    role: str | None = None
    skills: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    verified: bool = True
    confidence: float = Field(default=1.0, ge=0, le=1)
    source_type: str | None = None
    source_document: str | None = None
    source_section: str | None = None
    supporting_text: str | None = None
    user_edited: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompensationPreferences(BaseModel):
    minimum_base_salary: int | None = None
    preferred_base_salary: int | None = None
    minimum_total_compensation: int | None = None
    salary_is_hard_filter: bool = False
    below_minimum_penalty: float = Field(default=25, ge=0, le=100)


class CandidateProfile(BaseModel):
    identity: Identity = Field(default_factory=Identity)
    professional_summary: ProfileItem | None = None
    roles: list[ProfileItem] = Field(default_factory=list)
    experience: list[ProfileItem] = Field(default_factory=list)
    education: list[ProfileItem] = Field(default_factory=list)
    skills: list[ProfileItem] = Field(default_factory=list)
    research: list[ProfileItem] = Field(default_factory=list)
    publications: list[ProfileItem] = Field(default_factory=list)
    patents: list[ProfileItem] = Field(default_factory=list)
    projects: list[ProfileItem] = Field(default_factory=list)
    technical_domains: list[ProfileItem] = Field(default_factory=list)
    leadership: list[ProfileItem] = Field(default_factory=list)

    @computed_field
    @property
    def portfolio_url(self) -> HttpUrl | None:
        return self.identity.portfolio_url

    @computed_field
    @property
    def linkedin_url(self) -> HttpUrl | None:
        return self.identity.linkedin_url


class JobPreferences(BaseModel):
    preferred_titles: list[str] = Field(default_factory=list)
    excluded_titles: list[str] = Field(default_factory=list)
    preferred_domains: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    remote_allowed: bool = True
    hybrid_allowed: bool = True
    onsite_allowed: bool = True
    minimum_salary: int | None = None
    seniority: list[str] = Field(default_factory=list)
    employment_types: list[str] = Field(default_factory=list)
    preferred_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    preferred_company_types: list[str] = Field(default_factory=list)
    required_keywords: list[str] = Field(default_factory=list)
    excluded_keywords: list[str] = Field(default_factory=list)
    minimum_fit_score: float = 0
    sponsorship_requirement: str | None = None
    compensation: CompensationPreferences = Field(default_factory=CompensationPreferences)
    commutable_locations: list[str] = Field(default_factory=list)
    relocation_willing: bool | None = None
    work_authorization: str | None = None
    sponsorship_required: bool | None = None


class CandidateApplicationPolicy(BaseModel):
    """User-owned application facts kept outside the public source tree."""
    answers: dict[str, Any] = Field(default_factory=dict)
    work_authorization: dict[str, str] = Field(default_factory=dict)
    discovery_source_preferences: list[str] = Field(default_factory=lambda: ["LinkedIn", "Social Media", "Search Engine", "Company Website", "Other"])
