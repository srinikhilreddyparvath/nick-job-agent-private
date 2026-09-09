from typing import Literal

from pydantic import BaseModel, Field

from app.models.profile import CandidateProfile, EvidenceRecord, JobPreferences


class ResumeMetadata(BaseModel):
    document_id: str
    filename: str
    file_type: Literal["pdf", "docx", "txt"]
    text_length: int
    page_count: int | None = None
    file_size: int = 0
    extraction_method: Literal["PDF_TEXT", "DOCX_TEXT", "TXT_DECODE", "OCR", "NONE"] = "NONE"
    text_quality_status: Literal["GOOD", "USABLE", "LOW_QUALITY", "SCANNED_OR_IMAGE_ONLY", "EMPTY", "CORRUPTED"] = "GOOD"
    extraction_status: Literal["EXTRACTED", "PARTIAL", "NEEDS_ATTENTION"] = "EXTRACTED"
    normalization_status: Literal["COMPLETED", "NEEDS_ATTENTION"] = "COMPLETED"
    detected_sections: list[str] = Field(default_factory=list)
    model_counts: dict[str, int] = Field(default_factory=dict)
    grounded_counts: dict[str, int] = Field(default_factory=dict)


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
    start_date: str | None = None
    end_date: str | None = None
    location: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    accomplishments: list[str] = Field(default_factory=list)
    source_section: str = "unspecified"
    supporting_text: str = ""
    confidence: float = Field(ge=0, le=1)


class ResumeExtractionPayload(BaseModel):
    professional_name: str | None = None
    professional_summary: ExtractedResumeItem | None = None
    employment: list[ExtractedEmployment] = Field(default_factory=list)
    skills: list[ExtractedResumeItem] = Field(default_factory=list)
    education: list[ExtractedResumeItem] = Field(default_factory=list)
    projects: list[ExtractedResumeItem] = Field(default_factory=list)
    certifications: list[ExtractedResumeItem] = Field(default_factory=list)
    domains: list[ExtractedResumeItem] = Field(default_factory=list)
    technologies: list[ExtractedResumeItem] = Field(default_factory=list)
    research: list[ExtractedResumeItem] = Field(default_factory=list)
    publications: list[ExtractedResumeItem] = Field(default_factory=list)
    patents: list[ExtractedResumeItem] = Field(default_factory=list)
    leadership: list[ExtractedResumeItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    confirm_replacement: bool = False
    preferences_reviewed: bool = False


class OnboardingState(BaseModel):
    profile: CandidateProfile
    evidence: list[EvidenceRecord]
    preferences: JobPreferences
    configured: bool
    replacement_pending: bool = False
