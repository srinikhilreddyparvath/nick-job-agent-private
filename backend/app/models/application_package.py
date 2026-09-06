from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PackageStatus(StrEnum):
    draft="DRAFT"; review_required="REVIEW_REQUIRED"; ready_for_review="READY_FOR_REVIEW"; approved="APPROVED"; rejected="REJECTED"; stale="STALE"; generation_failed="GENERATION_FAILED"
class ReviewStatus(StrEnum): pass_="PASS"; pass_with_warnings="PASS_WITH_WARNINGS"; fail="FAIL"; human_review_required="HUMAN_REVIEW_REQUIRED"
class AnswerType(StrEnum): approved_structured="APPROVED_STRUCTURED"; evidence_generated="EVIDENCE_GENERATED"; human_review_required="HUMAN_REVIEW_REQUIRED"
class AnswerLength(StrEnum): short="SHORT"; medium="MEDIUM"; long="LONG"
class TransformationType(StrEnum): unchanged="UNCHANGED"; reordered="REORDERED"; paraphrased="PARAPHRASED"; condensed="CONDENSED"; combined_supported="COMBINED_SUPPORTED"


class JobRequirement(BaseModel):
    requirement_id:str; category:str; text:str; importance:int=Field(ge=1,le=5); required_vs_preferred:str
    candidate_match:str="unknown"; supporting_evidence_ids:list[str]=Field(default_factory=list); gap:str|None=None; confidence:float=Field(default=.5,ge=0,le=1)


class ApplicationStrategy(BaseModel):
    job_id:int; target_role_family:str; primary_positioning:str; top_3_themes:list[str]=Field(default_factory=list,max_length=3)
    top_requirements_to_emphasize:list[str]=Field(default_factory=list); secondary_requirements:list[str]=Field(default_factory=list)
    known_gaps:list[str]=Field(default_factory=list); resume_emphasis:list[str]=Field(default_factory=list); resume_deemphasis:list[str]=Field(default_factory=list)
    cover_letter_recommended:bool=False; application_risk:str="medium"; recommended_action:str="human_review"


class GroundedText(BaseModel):
    text:str; evidence_ids:list[str]=Field(default_factory=list)


class ResumeBullet(BaseModel):
    id:str; section:str; employer_or_context:str; generated_text:str; source_evidence_ids:list[str]=Field(min_length=1)
    source_resume_text:str; transformation_type:TransformationType; validation_status:str="pending"; validation_confidence:float=0
    original_model_text:str|None=None; edited_text:str|None=None


class TailoredResumeData(BaseModel):
    professional_name:str; email:str; phone:str; location:str|None=None; portfolio_url:str|None=None; linkedin_url:str|None=None
    target_company:str; target_role:str; summary:list[GroundedText]=Field(default_factory=list); bullets:list[ResumeBullet]=Field(default_factory=list)
    skills:list[GroundedText]=Field(default_factory=list); education:list[GroundedText]=Field(default_factory=list); page_length:int=2


class ApplicationQuestionInput(BaseModel):
    question_text:str=Field(min_length=2); required:bool=True; character_limit:int|None=Field(default=None,ge=1,le=10000); answer_length:AnswerLength=AnswerLength.medium; source:str="manual"


class ApplicationAnswer(BaseModel):
    id:str; question_text:str; question_type:str="other"; required:bool=True; detected_category:str="other"; source:str="manual"
    answer:str|None=None; original_model_answer:str|None=None; edited_answer:str|None=None; answer_status:str="DRAFT"; answer_type:AnswerType
    evidence_ids:list[str]=Field(default_factory=list); confidence:float=0; character_limit:int|None=None; requires_human_review:bool=False; reusable:bool=False
    @model_validator(mode="after")
    def enforce_limit(self):
        if self.answer and self.character_limit and len(self.answer)>self.character_limit: raise ValueError("Answer exceeds character limit")
        return self


class ReviewFinding(BaseModel):
    severity:str; affected_artifact:str; claim:str; evidence_ids:list[str]=Field(default_factory=list); recommended_action:str
class ApplicationReview(BaseModel):
    status:ReviewStatus; findings:list[ReviewFinding]=Field(default_factory=list); reasoning_summary:str; requires_human_review:bool=False


class ApplicationDraft(BaseModel):
    strategy:ApplicationStrategy; requirements:list[JobRequirement]=Field(default_factory=list); summary:list[GroundedText]=Field(default_factory=list)
    resume_bullets:list[ResumeBullet]=Field(default_factory=list); skills:list[GroundedText]=Field(default_factory=list)
    application_answers:list[ApplicationAnswer]=Field(default_factory=list); cover_letter:str|None=None; cover_letter_evidence_ids:list[str]=Field(default_factory=list)
    recruiter_summary:list[GroundedText]=Field(default_factory=list)


class ApplicationGenerationDraft(BaseModel):
    """Minimal provider output; deterministic requirements are added by the service."""
    strategy:ApplicationStrategy
    summary:list[GroundedText]=Field(default_factory=list)
    resume_bullets:list[ResumeBullet]=Field(default_factory=list)
    skills:list[GroundedText]=Field(default_factory=list)
    application_answers:list[ApplicationAnswer]=Field(default_factory=list)
    cover_letter:str|None=None
    cover_letter_evidence_ids:list[str]=Field(default_factory=list)
    recruiter_summary:list[GroundedText]=Field(default_factory=list)


class ApplicationPackageRead(BaseModel):
    id:int; job_id:int; status:PackageStatus; resume_version_id:str; resume_strategy:ApplicationStrategy; tailored_resume_path:str|None=None
    tailored_resume_preview:TailoredResumeData; job_requirements:list[JobRequirement]=Field(default_factory=list); cover_letter:str|None=None; cover_letter_evidence_ids:list[str]=Field(default_factory=list); cover_letter_required:bool=False; cover_letter_status:str="NOT_GENERATED"
    application_answers:list[ApplicationAnswer]=Field(default_factory=list); application_summary:list[GroundedText]=Field(default_factory=list)
    fit_analysis_id:int|None=None; research_report_id:int|None=None; evidence_ids_used:list[str]=Field(default_factory=list)
    unsupported_claims_removed:list[str]=Field(default_factory=list); review_findings:list[ReviewFinding]=Field(default_factory=list)
    review_status:ReviewStatus|None=None; requires_human_review:bool=True; human_review_reasons:list[str]=Field(default_factory=list)
    provider:str; model:str; prompt_versions:dict[str,str]=Field(default_factory=dict); input_tokens:int=0; output_tokens:int=0; cached_tokens:int=0; estimated_cost:float=0; latency_ms:int=0
    evidence_version:str; job_fingerprint:str; package_fingerprint:str; created_at:datetime; updated_at:datetime; approved_at:datetime|None=None
    model_config=ConfigDict(from_attributes=True)


class PackageGenerateRequest(BaseModel):
    questions:list[ApplicationQuestionInput]=Field(default_factory=list); use_mock:bool=False; force:bool=False; cover_letter_requested:bool=False; resume_pages:int=Field(default=2,ge=1,le=2)
class PackageEditAnswerRequest(BaseModel): answer:str
class PackageEditCoverLetterRequest(BaseModel): cover_letter:str
class PackageEditResumeBulletRequest(BaseModel): text:str
class PackageApproveRequest(BaseModel): artifact:str="package"; save_reusable_answers:bool=False
class PackageResponse(BaseModel): status:str; package:ApplicationPackageRead|None=None; error:str|None=None; application_agent_run_id:int|None=None; reviewer_agent_run_id:int|None=None
