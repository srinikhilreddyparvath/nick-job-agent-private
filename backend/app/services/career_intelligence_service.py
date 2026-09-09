from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.db.models import AgentRunRecord, JobRecord, JobSourceRecord, ScanRunRecord, JobScoreRecord
from app.models.career_intelligence import CareerIntelligenceRun
from app.services.candidate_context_service import current_context, assert_current
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.discovery_catalog_service import DiscoveryCatalogService
from app.services.job_service import JobService
from app.services.llm_service import configured_llm_service
from app.services.scan_orchestrator import ScanOrchestrator
from app.services.semantic_analysis_service import SemanticAnalysisService


STAGES = {
    "queued": "Waiting for the local worker",
    "scanning_sources": "Scanning configured public sources",
    "evaluating_fit": "Evaluating deterministic fit",
    "semantic_analysis": "AI analyzing the bounded candidate set",
    "ranking": "Ranking opportunities",
    "completed": "Jobs worth your attention are ready",
    "failed": "Career-intelligence run failed",
}


class CareerIntelligenceService:
    """Discovery and fit analysis that never invokes application automation."""

    def __init__(self, settings: Settings | None = None, scanner=None, semantic=None):
        self.settings = settings or get_settings()
        self.scanner = scanner or ScanOrchestrator()
        self.semantic = semantic

    def enqueue(self, db, *, trigger: str = "user", scan_required: bool = True, scan_id: int | None = None):
        context = current_context()
        if context.pending: raise ValueError("Review and approve the uploaded resume and preferences before finding jobs")
        active = db.scalar(select(AgentRunRecord).where(AgentRunRecord.agent_type == "career_intelligence", AgentRunRecord.status.in_(["queued", "running"])).order_by(AgentRunRecord.id.desc()))
        if active:
            return active
        if trigger == "user" and not CandidatePersistenceService(self.settings).state().configured:
            raise ValueError("Complete and approve candidate onboarding before finding jobs")
        existing_jobs = db.scalar(select(func.count()).select_from(JobRecord)) or 0
        existing_evaluations = db.scalar(select(func.count()).select_from(JobScoreRecord)) or 0
        if existing_jobs and existing_evaluations < existing_jobs:
            scan_required = False
        source_count = min(self.settings.discovery_max_sources_per_run,(db.scalar(select(func.count()).select_from(JobSourceRecord).where(JobSourceRecord.enabled.is_(True))) or 0)+len(DiscoveryCatalogService(self.settings).catalog()))
        if scan_required and not source_count:raise ValueError("No starter or user-added discovery sources are available")
        record = AgentRunRecord(agent_type="career_intelligence", objective="Discover, analyze, and globally rank career opportunities", status="queued", **context.ownership(), input_state_json={"trigger": trigger, "scan_required": scan_required, "scan_id": scan_id, "source_count": source_count, "semantic_budget": self.settings.llm_max_semantic_analyses_per_scan}, actions_json=[{"stage": "queued", "message": STAGES["queued"]}])
        db.add(record);db.commit();db.refresh(record);return record

    @staticmethod
    def _progress(db, run, stage: str, **details):
        actions=list(run.actions_json or []);actions.append({"stage":stage,"message":STAGES[stage],**details});run.actions_json=actions
        db.add(run);db.commit();db.refresh(run)

    @staticmethod
    def recover_abandoned(db, worker_id: str) -> int:
        """Recover runs owned by a worker process that no longer exists.

        RoleCall V0.1 runs one discovery worker. A new process has a new worker
        identifier, so any RUNNING run owned by another process is abandoned.
        """
        rows = db.scalars(select(AgentRunRecord).where(AgentRunRecord.agent_type == "career_intelligence", AgentRunRecord.status == "running")).all()
        recovered = 0
        for row in rows:
            state = dict(row.input_state_json or {})
            if state.get("worker_id") == worker_id:
                continue
            row.status = "failed"
            row.completed_at = datetime.now(timezone.utc)
            row.errors_json = [{"error": "WORKER_INTERRUPTED", "recoverable": True}]
            row.actions_json = [*(row.actions_json or []), {"stage": "failed", "message": "The local worker was interrupted. Jobs already collected are safe; try Find Jobs again."}]
            recovered += 1
        abandoned_scans = db.scalars(select(ScanRunRecord).where(ScanRunRecord.status == "running")).all()
        for scan in abandoned_scans:
            scan.status = "failed"
            scan.completed_at = datetime.now(timezone.utc)
            scan.errors_json = [*(scan.errors_json or []), {"level": "run", "error": "WORKER_INTERRUPTED", "recoverable": True}]
        if recovered or abandoned_scans:
            db.commit()
        return recovered

    def process_next(self, db, worker_id: str | None = None):
        run=db.scalar(select(AgentRunRecord).where(AgentRunRecord.agent_type=="career_intelligence",AgentRunRecord.status=="queued").order_by(AgentRunRecord.id).with_for_update(skip_locked=True))
        if not run:return None
        state=dict(run.input_state_json or {});state["worker_id"]=worker_id;run.input_state_json=state
        run.status="running";run.started_at=datetime.now(timezone.utc);db.commit();db.refresh(run)
        run_id=run.id
        try:return self.execute(db,run)
        except Exception as exc:
            db.rollback()
            run=db.get(AgentRunRecord,run_id)
            run.status="failed";run.completed_at=datetime.now(timezone.utc);run.errors_json=[{"error":type(exc).__name__,"recoverable":True}]
            self._progress(db,run,"failed",message="We hit a problem while processing a job source. Your profile and jobs already collected are safe. Try again.")
            return run

    def execute(self, db, run):
        context = current_context()
        if context.pending or run.candidate_context_key != context.key:
            raise ValueError("Candidate changed; start a new Find Jobs run")
        state=dict(run.input_state_json or {});scan_id=state.get("scan_id")
        if state.get("scan_required",True):
            sources=DiscoveryCatalogService(self.settings).select(db,CandidatePersistenceService(self.settings).state().preferences)
            self._progress(db,run,"scanning_sources",source_count=len(sources))
            def scan_progress(scan):
                nonlocal scan_id
                scan_id=scan.id
                current=db.get(AgentRunRecord,run.id)
                state=dict(current.input_state_json or {});state["scan_id"]=scan.id;current.input_state_json=state
                current.output_state_json={**(current.output_state_json or {}),"scan_id":scan.id,"jobs_found":scan.jobs_fetched,"unique_jobs":scan.jobs_added,"sources_scanned":scan.successful_source_count+scan.failed_source_count,"sources_succeeded":scan.successful_source_count,"sources_failed":scan.failed_source_count}
                db.add(current);db.commit()
            scan=self.scanner.scan(db,sources,on_progress=scan_progress);scan_id=scan.id
            found=scan.jobs_fetched;unique=scan.jobs_added
            if scan.status=="failed":
                output={"scan_id":scan_id,"jobs_found":found,"unique_jobs":unique,"promising_jobs":0,"semantic_selected":0,"semantic_completed":0,"semantic_failed":0,"ranked_jobs":0,"companies_represented":0,"sources_scanned":scan.source_count,"sources_succeeded":scan.successful_source_count,"sources_failed":scan.failed_source_count,"deterministic_fallback":True,"estimated_cost":0.0}
                run.status="failed";run.completed_at=datetime.now(timezone.utc);run.errors_json=scan.errors_json or [];run.output_state_json=output
                self._progress(db,run,"failed",message="No job sources could be reached. Check your connection and try Find Jobs again.",**output)
                return run
        else:
            previous=db.get(ScanRunRecord,scan_id) if scan_id else None
            found=previous.jobs_fetched if previous else db.scalar(select(func.count()).select_from(JobRecord)) or 0
            unique=previous.jobs_added if previous else 0
        self._progress(db,run,"evaluating_fit",jobs_found=found,unique_jobs=unique)
        assert_current(context)
        JobService().evaluate_catalog(db, context)
        candidates = [job for job in JobService().list(db, limit=500).items if job.fit_score is not None and job.fit_score >= 55]
        candidates.sort(key=lambda job:(job.semantic_analysis_status == "COMPLETE", -(job.fit_score or 0), job.id))
        budget=max(0,self.settings.llm_max_semantic_analyses_per_scan);selected=candidates[:budget]
        completed=failed=0;cost=0.0;provider=model=None
        self._progress(db,run,"semantic_analysis",promising_jobs=len(candidates),selected=len(selected),completed=0)
        if self.settings.llm_enabled and selected:
            semantic=self.semantic
            if semantic is None:
                llm=configured_llm_service(settings=self.settings);semantic=SemanticAnalysisService(llm,settings=self.settings)
            provider=semantic.llm.provider.name;model=semantic.llm.provider.model
            for job in selected:
                try:
                    result=semantic.analyze(db,job.id)
                    if result.report:completed+=1;cost+=0 if getattr(result.report,"cache_hit",False) else result.report.estimated_cost
                    else:failed+=1
                except Exception:failed+=1
                self._progress(db,run,"semantic_analysis",promising_jobs=len(candidates),selected=len(selected),completed=completed,failed=failed)
        assert_current(context)
        ranked_result=JobService().list(db,limit=500,diversified=False);ranked=ranked_result.total;companies=len({job.company.casefold() for job in ranked_result.items})
        self._progress(db,run,"ranking",ranked_jobs=ranked,companies_represented=companies)
        scan_record=db.get(ScanRunRecord,scan_id) if scan_id else None
        run.status="completed";run.completed_at=datetime.now(timezone.utc);run.provider=provider;run.model=model;run.estimated_cost=round(cost,8);run.output_state_json={"scan_id":scan_id,"jobs_found":found,"unique_jobs":unique,"promising_jobs":len(candidates),"semantic_selected":len(selected) if self.settings.llm_enabled else 0,"semantic_completed":completed,"semantic_failed":failed,"ranked_jobs":ranked,"companies_represented":companies,"sources_scanned":scan_record.source_count if scan_record else 0,"sources_succeeded":scan_record.successful_source_count if scan_record else 0,"sources_failed":scan_record.failed_source_count if scan_record else 0,"deterministic_fallback":not self.settings.llm_enabled or failed>0,"estimated_cost":round(cost,8)}
        if not ranked:message="Search completed, but no qualifying jobs matched your current preferences. Try broadening your preferences or add a company to watch."
        elif scan_record and scan_record.failed_source_count:message=f"Jobs worth your attention are ready. {scan_record.failed_source_count} source{' was' if scan_record.failed_source_count==1 else 's were'} unavailable; results from healthy sources were preserved."
        else:message=STAGES["completed"]
        self._progress(db,run,"completed",message=message,**run.output_state_json);return run

    @staticmethod
    def read(run: AgentRunRecord) -> CareerIntelligenceRun:
        output=run.output_state_json or {};actions=run.actions_json or [{}];current=actions[-1];inputs=run.input_state_json or {};progress={}
        for action in actions:progress.update({key:value for key,value in action.items() if key not in {"stage","message"}})
        return CareerIntelligenceRun(id=run.id,status=run.status,stage=current.get("stage",run.status),source_count=inputs.get("source_count",0),sources_scanned=output.get("sources_scanned",0),sources_succeeded=output.get("sources_succeeded",0),sources_failed=output.get("sources_failed",0),companies_represented=output.get("companies_represented",progress.get("companies_represented",0)),jobs_found=output.get("jobs_found",progress.get("jobs_found",0)),unique_jobs=output.get("unique_jobs",progress.get("unique_jobs",0)),promising_jobs=output.get("promising_jobs",progress.get("promising_jobs",0)),semantic_selected=output.get("semantic_selected",progress.get("selected",0)),semantic_completed=output.get("semantic_completed",progress.get("completed",0)),semantic_failed=output.get("semantic_failed",progress.get("failed",0)),ranked_jobs=output.get("ranked_jobs",progress.get("ranked_jobs",0)),provider=run.provider,model=run.model,estimated_cost=run.estimated_cost or 0,message=current.get("message",STAGES.get(run.status,run.status)),errors=run.errors_json or [],started_at=run.started_at,completed_at=run.completed_at)
