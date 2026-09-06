from enum import StrEnum

from pydantic import BaseModel, Field


class OpportunityRecommendation(StrEnum):
    apply_now="APPLY_NOW"
    apply="APPLY"
    contact_first="CONTACT_FIRST"
    stretch="STRETCH"
    skip="SKIP"


class ConstraintState(StrEnum):
    match="MATCH"
    mismatch="MISMATCH"
    unknown="UNKNOWN"


class GapKind(StrEnum):
    experience="EXPERIENCE_GAP"
    evidence="EVIDENCE_OR_WORDING_GAP"
    unknown="UNKNOWN_NEEDS_CLARIFICATION"


class EvidenceMatch(BaseModel):
    reason:str
    evidence_ids:list[str]=Field(default_factory=list)


class OpportunityGap(BaseModel):
    text:str
    kind:GapKind


class ConstraintAssessment(BaseModel):
    location:ConstraintState=ConstraintState.unknown
    work_arrangement:ConstraintState=ConstraintState.unknown
    compensation:ConstraintState=ConstraintState.unknown
    visa:ConstraintState=ConstraintState.unknown
    employment_type:ConstraintState=ConstraintState.unknown
    seniority:ConstraintState=ConstraintState.unknown
    hard_blockers:list[str]=Field(default_factory=list)


class OpportunityScore(BaseModel):
    overall_score:float=Field(ge=0,le=100)
    deterministic_fit:float|None=None
    semantic_fit:float|None=None
    technical_fit:float|None=None
    career_fit:float|None=None
    research_fit:float|None=None
    skills_fit:float|None=None
    location_fit:float|None=None
    compensation_fit:float|None=None
    visa_fit:float|None=None
    freshness_score:float|None=None
    application_effort_score:float|None=None
    confidence:float=Field(ge=0,le=1)
    recommendation:OpportunityRecommendation
    recommendation_reason:str
    why_you_match:list[EvidenceMatch]=Field(default_factory=list)
    real_gaps:list[OpportunityGap]=Field(default_factory=list)
    constraints:ConstraintAssessment=Field(default_factory=ConstraintAssessment)


class PublicContact(BaseModel):
    person_name:str
    title:str
    company:str
    public_profile_url:str
    source_url:str
    contact_type:str
    relevance_score:float=Field(ge=0,le=100)
    relevance_reason:str
    confidence:float=Field(ge=0,le=1)
    verified_hiring_manager:bool=False
