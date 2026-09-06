from typing import Literal

from pydantic import BaseModel, Field

from app.models.profile import CandidateProfile, EvidenceRecord, JobPreferences


class ResumeMetadata(BaseModel):
    document_id: str
    filename: str
    file_type: Literal["pdf", "docx", "txt"]
    text_length: int
    page_count: int | None = None
    extraction_status: Literal["EXTRACTED", "PARTIAL"] = "EXTRACTED"


class CandidateExtractionDraft(BaseModel):
    profile: CandidateProfile
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ExtractedResumeItem(BaseModel):
    value: str
    source_section: str
    supporting_text: str
    confidence: float = Field(ge=0, le=1)


class ExtractedEmployment(BaseModel):
    employer: str
    title: str
    start_date: str | None
    end_date: str | None
    responsibilities: list[str]
    accomplishments: list[str]
    source_section: str
    supporting_text: str
    confidence: float = Field(ge=0, le=1)


class ResumeExtractionPayload(BaseModel):
    professional_name: str | None
    professional_summary: ExtractedResumeItem | None
    employment: list[ExtractedEmployment]
    skills: list[ExtractedResumeItem]
    education: list[ExtractedResumeItem]
    projects: list[ExtractedResumeItem]
    certifications: list[ExtractedResumeItem]
    domains: list[ExtractedResumeItem]
    technologies: list[ExtractedResumeItem]
    warnings: list[str]


class ResumeIngestionResult(BaseModel):
    metadata: ResumeMetadata
    draft: CandidateExtractionDraft
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0


class OnboardingApprovalRequest(BaseModel):
    profile: CandidateProfile
    evidence: list[EvidenceRecord]
    preferences: JobPreferences


class OnboardingState(BaseModel):
    profile: CandidateProfile
    evidence: list[EvidenceRecord]
    preferences: JobPreferences
    configured: bool
