import json
from pathlib import Path
from typing import Any
from pydantic import BaseModel,Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CompanyRecord,JobFeedbackRecord,JobScoreRecord
from app.models.job import Job
from app.models.policy import ClaimValidationRequest,ClaimValidationResult
from app.models.profile import EvidenceRecord,JobPreferences
from app.services.claim_validator import EvidenceClaimValidator
from app.services.evidence_service import EvidenceService
from app.services.job_service import JobService
from app.services.tool_registry import AgentTool,ToolRegistry

class JobIdInput(BaseModel):job_id:int
class EvidenceQueryInput(BaseModel):query:str;limit:int=Field(default=10,ge=1,le=20)
class EvidenceResults(BaseModel):items:list[EvidenceRecord]
class SemanticEvidenceResults(BaseModel):items:list[dict]
class EmptyInput(BaseModel):pass
class ValueOutput(BaseModel):value:Any=None
class FeedbackOutput(BaseModel):human_label:str|None=None;human_notes:str|None=None
class CompanyOutput(BaseModel):id:int|None=None;name:str;website_url:str|None=None;careers_url:str|None=None

def build_phase3_tool_registry(db:Session,evidence:EvidenceService|None=None)->ToolRegistry:
    evidence=evidence or EvidenceService();jobs=JobService();registry=ToolRegistry()
    def get_job(job_id):
        record=jobs.get(db,job_id)
        if not record:raise ValueError("Job not found")
        return jobs.to_schema(record)
    def search_candidate_evidence(query,limit):
        matches=evidence.search(text_query=query)
        return EvidenceResults(items=(matches or evidence.all())[:limit])
    def search_semantic_evidence(query,limit):return SemanticEvidenceResults(items=[x.model_dump(mode="json") for x in evidence.search_hybrid(db,query,limit=limit)])
    def deterministic_score(job_id):
        row=db.scalar(select(JobScoreRecord).where(JobScoreRecord.job_id==job_id).order_by(JobScoreRecord.created_at.desc()));return ValueOutput(value=row.overall_score if row else None)
    def role_family(job_id):return ValueOutput(value=get_job(job_id).role_family)
    def preferences():
        path=Path(__file__).resolve().parents[3]/"data"/"job_preferences.example.json";return ValueOutput(value=JobPreferences.model_validate_json(path.read_text(encoding="utf-8")).model_dump(mode="json"))
    def feedback(job_id):
        row=db.scalar(select(JobFeedbackRecord).where(JobFeedbackRecord.job_id==job_id));return FeedbackOutput(human_label=row.human_label if row else None,human_notes=row.human_notes if row else None)
    def company(job_id):
        job=get_job(job_id);row=db.scalar(select(CompanyRecord).where(CompanyRecord.canonical_name==job.canonical_company));return CompanyOutput(id=row.id if row else None,name=row.name if row else job.company,website_url=row.website_url if row else None,careers_url=row.careers_url if row else None)
    def validate_claim(generated_claim,supporting_evidence_ids):return EvidenceClaimValidator(evidence).validate(ClaimValidationRequest(generated_claim=generated_claim,supporting_evidence_ids=supporting_evidence_ids))
    registry.register(AgentTool("get_job","Load one persisted normalized job",JobIdInput,Job,{"fit","research"},get_job))
    registry.register(AgentTool("search_candidate_evidence","Search verified canonical evidence deterministically",EvidenceQueryInput,EvidenceResults,{"fit","research"},search_candidate_evidence))
    registry.register(AgentTool("search_semantic_evidence","Hybrid semantic search over verified evidence",EvidenceQueryInput,SemanticEvidenceResults,{"fit"},search_semantic_evidence))
    registry.register(AgentTool("get_deterministic_score","Load the stored deterministic baseline score",JobIdInput,ValueOutput,{"fit"},deterministic_score))
    registry.register(AgentTool("get_role_family","Load deterministic/final role-family state",JobIdInput,ValueOutput,{"fit"},role_family))
    registry.register(AgentTool("get_job_preferences","Load configured job preferences",EmptyInput,ValueOutput,{"fit"},preferences))
    registry.register(AgentTool("get_human_feedback_history","Load Nick's current feedback for the job",JobIdInput,FeedbackOutput,{"fit"},feedback))
    registry.register(AgentTool("validate_claim","Validate a candidate claim against supplied evidence IDs",ClaimValidationRequest,ClaimValidationResult,{"fit"},validate_claim))
    registry.register(AgentTool("get_company","Load company registry context for a job",JobIdInput,CompanyOutput,{"research"},company))
    return registry
