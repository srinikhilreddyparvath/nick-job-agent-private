from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.role_family import RoleFamily


class RetrievalMethod(StrEnum): semantic="semantic"; deterministic="deterministic"; hybrid="hybrid"
class SemanticEvidenceResult(BaseModel):
    evidence_id:str; statement:str; score:float=Field(ge=0,le=1); retrieval_method:RetrievalMethod
class EmbeddingVector(BaseModel):
    vector:list[float]; provider:str; model:str; embedding_version:str; generated_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class CitedStrength(BaseModel):
    statement:str; evidence_ids:list[str]=Field(min_length=1)
class RequirementAssessment(BaseModel):
    requirement:str; assessment:str; evidence_ids:list[str]=Field(default_factory=list)
class SemanticFitReport(BaseModel):
    job_id:int; role_family:RoleFamily; semantic_fit_score:float=Field(ge=0,le=100); confidence:float=Field(ge=0,le=1)
    strengths:list[CitedStrength]=Field(default_factory=list); gaps:list[str]=Field(default_factory=list)
    requirement_matches:list[RequirementAssessment]=Field(default_factory=list); requirement_gaps:list[str]=Field(default_factory=list)
    evidence_ids:list[str]=Field(default_factory=list); career_transition_analysis:str|None=None
    research_alignment:str=""; technical_alignment:str=""; experience_alignment:str=""
    recommended_action:str; reasoning_summary:str; unsupported_claims:list[str]=Field(default_factory=list); requires_human_review:bool=False
    deterministic_score:float|None=None; blended_score:float|None=None
    provider:str=""; model:str=""; prompt_version:str="fit_analysis_v1"; latency_ms:int=0; input_tokens:int=0; output_tokens:int=0; estimated_cost:float=0
    cache_hit:bool=False; created_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
    @model_validator(mode="after")
    def cited_strengths_are_in_evidence_set(self):
        used={item for strength in self.strengths for item in strength.evidence_ids}
        self.evidence_ids=sorted(set(self.evidence_ids)|used)
        return self
class SemanticRoleClassification(BaseModel):
    role_family:RoleFamily; confidence:float=Field(ge=0,le=1); reasoning:str; signals:list[str]=Field(default_factory=list)
class ResolvedRoleClassification(BaseModel):
    deterministic_family:RoleFamily; deterministic_confidence:float; semantic_family:RoleFamily|None=None; semantic_confidence:float|None=None; final_family:RoleFamily; classification_resolution_method:str
class ResearchSource(BaseModel):
    url:str; title:str; source_type:str; retrieved_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc)); excerpt:str
class JobResearchReport(BaseModel):
    job_id:int; company_summary:str; role_summary:str; likely_team_context:str=""; key_requirements:list[str]=Field(default_factory=list); preferred_requirements:list[str]=Field(default_factory=list); research_relevance:str=""; technical_relevance:str=""; career_opportunity:str=""; potential_risks:list[str]=Field(default_factory=list); questions_to_investigate:list[str]=Field(default_factory=list); source_citations:list[ResearchSource]=Field(default_factory=list)
    provider:str=""; model:str=""; prompt_version:str="research_agent_v1"; latency_ms:int=0; input_tokens:int=0; output_tokens:int=0; estimated_cost:float=0; cache_hit:bool=False; generated_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
class ModelStatus(BaseModel):
    llm_enabled:bool; provider_configured:bool; provider:str|None=None; model_configured:bool; model:str|None=None; embedding_provider_configured:bool; embedding_provider:str|None=None; embedding_model:str|None=None; embedding_index_status:str; evidence_version:str
class AnalysisRequest(BaseModel):
    refresh:bool=False; use_mock:bool=False
class ResearchRequest(BaseModel):
    refresh:bool=False; use_mock:bool=False
class AnalysisResponse(BaseModel):
    status:str; report:SemanticFitReport|None=None; deterministic_score:float|None=None; error:str|None=None; agent_run_id:int|None=None
class ResearchResponse(BaseModel):
    status:str; report:JobResearchReport|None=None; error:str|None=None; agent_run_id:int|None=None
class ToolCall(BaseModel):
    name:str; arguments:dict[str,Any]=Field(default_factory=dict)
class LLMUsage(BaseModel): input_tokens:int=0; output_tokens:int=0; estimated_cost:float=0
class LLMResponse(BaseModel):
    content:dict[str,Any]|None=None; tool_calls:list[ToolCall]=Field(default_factory=list); usage:LLMUsage=Field(default_factory=LLMUsage); provider:str; model:str; latency_ms:int=0
class AgentToolDecision(BaseModel):
    action:str
    tool_name:str|None=None
    arguments:dict[str,Any]=Field(default_factory=dict)
    final_state:dict[str,Any]|None=None
