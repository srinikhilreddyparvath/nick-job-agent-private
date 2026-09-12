from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.researcher import ResearchAgent
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import AgentRunRecord,CompanyResearchRecord,SemanticAnalysisRecord
from app.models.agent import AgentRunRead
from app.models.semantic import AnalysisRequest,AnalysisResponse,JobResearchReport,ModelStatus,ResearchRequest,ResearchResponse,SemanticFitReport
from app.services.evidence_service import EvidenceService
from app.services.llm_service import LLMError,configured_llm_service
from app.services.research_service import ResearchService,SuppliedDataResearchProvider
from app.services.semantic_analysis_service import SemanticAnalysisService
from app.services.semantic_evidence_service import SemanticEvidenceIndex
from app.services.job_service import JobService
from app.services.agent_service import AgentRunService

router=APIRouter(tags=["semantic intelligence"])

@router.get("/models/status",response_model=ModelStatus)
def model_status(db:Session=Depends(get_db)):
    settings=get_settings();index=SemanticEvidenceIndex();version=index.version
    try:
        count=db.query(__import__("app.db.models",fromlist=["EvidenceEmbeddingRecord"]).EvidenceEmbeddingRecord).filter_by(evidence_version=version).count();status="ready" if count else "not_indexed"
    except Exception:status="unavailable"
    return ModelStatus(llm_enabled=settings.llm_enabled,provider_configured=bool(settings.llm_provider),provider=settings.llm_provider or None,model_configured=bool(settings.llm_model),model=settings.llm_model or None,embedding_provider_configured=bool(settings.embedding_provider),embedding_provider=settings.embedding_provider or None,embedding_model=settings.embedding_model or None,embedding_index_status=status,evidence_version=version)

@router.post("/evidence/reindex")
def reindex_evidence(force:bool=False,db:Session=Depends(get_db)):
    try:return SemanticEvidenceIndex().reindex(db,force)
    except Exception as exc:raise HTTPException(503,f"embedding_unavailable: {exc}") from exc

def llm_for(request):return configured_llm_service(use_mock=request.use_mock)

@router.post("/jobs/{job_id}/analyze",response_model=AnalysisResponse)
def analyze_job(job_id:int,request:AnalysisRequest,db:Session=Depends(get_db)):
    try:return SemanticAnalysisService(llm_for(request)).analyze(db,job_id,request.refresh)
    except LLMError as exc:
        record=JobService().get(db,job_id);deterministic=JobService().to_schema(record).fit_score if record else None
        run=AgentRunService().start(db,"fit","Produce an evidence-grounded semantic fit report",job_id,{"deterministic_score":deterministic});AgentRunService().fail(db,run,str(exc))
        return AnalysisResponse(status="fallback_deterministic",deterministic_score=deterministic,error=str(exc),agent_run_id=run.id)

@router.get("/jobs/{job_id}/analysis",response_model=SemanticFitReport)
def get_analysis(job_id:int,db:Session=Depends(get_db)):
    record=db.scalar(select(SemanticAnalysisRecord).where(SemanticAnalysisRecord.job_id==job_id).order_by(SemanticAnalysisRecord.created_at.desc()))
    from app.services.candidate_context_service import current_context, job_version
    context = current_context()
    from app.prompts.fit_analysis_v1 import VERSION as semantic_version
    job_record = JobService().get(db, job_id)
    if not record or not job_record or context.pending or record.prompt_version != semantic_version or record.report_json.get("job_version") != job_version(job_record):
        raise HTTPException(404,"Current candidate semantic analysis not found")
    try:
        context.validate_evidence(record.report_json.get("evidence_ids", []))
        for strength in record.report_json.get("strengths", []): context.validate_evidence(strength.get("evidence_ids", []))
    except ValueError as exc:
        raise HTTPException(404,"Current candidate semantic analysis not found") from exc
    return SemanticFitReport.model_validate(record.report_json)

@router.post("/jobs/{job_id}/research",response_model=ResearchResponse)
def research_job(job_id:int,request:ResearchRequest,db:Session=Depends(get_db)):
    try:
        llm=llm_for(request);provider=SuppliedDataResearchProvider() if request.use_mock else None;return ResearchService(llm,provider).research(db,job_id,request.refresh)
    except LLMError as exc:return ResearchResponse(status="unavailable",error=str(exc))

@router.get("/jobs/{job_id}/research",response_model=JobResearchReport)
def get_research(job_id:int,db:Session=Depends(get_db)):
    record=db.scalar(select(CompanyResearchRecord).where(CompanyResearchRecord.job_id==job_id).order_by(CompanyResearchRecord.generated_at.desc()))
    if not record:raise HTTPException(404,"Research report not found")
    return JobResearchReport.model_validate(record.report_json)

@router.get("/jobs/{job_id}/agent-runs",response_model=list[AgentRunRead])
def job_agent_runs(job_id:int,db:Session=Depends(get_db)):return db.scalars(select(AgentRunRecord).where(AgentRunRecord.job_id==job_id).order_by(AgentRunRecord.id.desc())).all()
