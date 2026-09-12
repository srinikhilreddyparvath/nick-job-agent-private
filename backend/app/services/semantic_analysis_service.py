import hashlib
import json
from datetime import datetime,timezone

from sqlalchemy import func,select
from sqlalchemy.orm import Session

from app.core.config import Settings,get_settings
from app.db.models import JobScoreRecord,SemanticAnalysisRecord
from app.models.policy import ClaimValidationRequest
from app.models.semantic import AnalysisResponse,SemanticFitReport
from app.prompts.fit_analysis_v1 import SYSTEM,VERSION
from app.services.agent_service import AgentRunService
from app.services.claim_validator import EvidenceClaimValidator
from app.services.evidence_service import EvidenceService
from app.services.job_service import JobService
from app.services.llm_service import LLMError,LLMService
from app.services.semantic_evidence_service import SemanticEvidenceIndex
from app.services.semantic_classifier import RoleClassificationPolicy,SemanticRoleFamilyClassifier
from app.services.phase3_tools import build_phase3_tool_registry
from app.services.candidate_context_service import current_context, assert_current, job_version
from app.services.agent_executor import BoundedLLMToolExecutor

class CostLimitError(RuntimeError):pass
class SemanticAnalysisService:
    def __init__(self,llm:LLMService,settings:Settings|None=None,evidence:EvidenceService|None=None,index:SemanticEvidenceIndex|None=None):self.llm=llm;self.settings=settings or get_settings();self.evidence=evidence or EvidenceService();self.index=index or SemanticEvidenceIndex(self.evidence);self.runs=AgentRunService();self.jobs=JobService();self.validator=EvidenceClaimValidator(self.evidence)
    def fingerprint(self,job,evidence_version):
        payload={"job_id":job.id,"job_version":job_version(job),"candidate_context":current_context().key,"description":job.description,"requirements":job.requirements,"preferred":job.preferred_qualifications,"evidence_version":evidence_version,"prompt":VERSION,"provider":self.llm.provider.name,"model":self.llm.provider.model};return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    def analyze(self,db:Session,job_id:int,refresh:bool=False)->AnalysisResponse:
        context_snapshot = current_context()
        if context_snapshot.pending: return AnalysisResponse(status="fallback_deterministic", error="Approve the replacement profile before analysis")
        self.evidence = EvidenceService(records=context_snapshot.evidence)
        self.index = SemanticEvidenceIndex(self.evidence, self.index.embeddings)
        self.validator = EvidenceClaimValidator(self.evidence)
        record=self.jobs.get(db,job_id)
        if not record:return AnalysisResponse(status="not_found",error="Job not found")
        # Direct Analyze is also an entry point: establish the candidate's family
        # gate before semantic scores can enter the ranked feed.
        self.jobs.evaluate_catalog(db, context_snapshot, job_id=job_id)
        tools=build_phase3_tool_registry(db,self.evidence);job=tools.invoke("fit","get_job",{"job_id":job_id});deterministic=job.fit_score
        run=self.runs.start(db,"fit","Produce an evidence-grounded semantic fit report",job_id,{"role_family":job.role_family,"deterministic_score":deterministic},provider=self.llm.provider.name,model=self.llm.provider.model,prompt_version=VERSION,temperature=0)
        try:
            today=datetime.now(timezone.utc).date();spent=db.scalar(select(func.coalesce(func.sum(SemanticAnalysisRecord.estimated_cost),0)).where(SemanticAnalysisRecord.created_at>=datetime.combine(today,datetime.min.time()))) or 0
            if self.settings.llm_daily_budget_usd<=spent:raise CostLimitError("Daily semantic-analysis budget reached")
            resolution=RoleClassificationPolicy(SemanticRoleFamilyClassifier(self.llm),self.settings).classify(job);record.deterministic_family=resolution.deterministic_family;record.deterministic_confidence=resolution.deterministic_confidence;record.semantic_family=resolution.semantic_family;record.semantic_confidence=resolution.semantic_confidence;record.final_family=resolution.final_family;record.classification_resolution_method=resolution.classification_resolution_method;record.role_family=resolution.final_family;db.commit();job.role_family=resolution.final_family
            version=self.index.version;fingerprint=self.fingerprint(job,version)
            cached=db.scalar(select(SemanticAnalysisRecord).where(SemanticAnalysisRecord.fingerprint==fingerprint))
            if cached and not refresh:
                assert_current(context_snapshot)
                context_snapshot.validate_evidence(cached.report_json.get("evidence_ids", []))
                for strength in cached.report_json.get("strengths", []): context_snapshot.validate_evidence(strength.get("evidence_ids", []))
                report=SemanticFitReport.model_validate(cached.report_json);report.cache_hit=True;self.runs.complete(db,run,report.model_dump(mode="json"),[{"step":1,"tool":"semantic_analysis_cache","status":"hit"}],evidence_ids_used=report.evidence_ids);return AnalysisResponse(status="completed",report=report,deterministic_score=deterministic,agent_run_id=run.id)
            query=" ".join([job.title,job.description,*job.requirements,*job.preferred_qualifications])[:12000]
            tool_actions=[];tool_usage=None;tool_latency=0
            try:
                retrieved_payload=tools.invoke("fit","search_semantic_evidence",{"query":query,"limit":10});retrieved=retrieved_payload.items;tool_actions=[{"step":1,"tool":"search_semantic_evidence","arguments":{"query_fingerprint":hashlib.sha256(query.encode()).hexdigest()[:12],"limit":10},"status":"completed","selection_method":"required_fit_stage"}]
            except Exception:retrieved=[]
            if not retrieved:
                fallback=[self.evidence.get_by_id(x) for x in job.matched_evidence_ids];fallback=[x for x in fallback if x] or self.evidence.all()[:8]
                evidence=[{"id":x.id,"statement":x.statement} for x in fallback]
            else:evidence=[{"id":x["evidence_id"],"statement":x["statement"],"score":x["score"]} for x in retrieved]
            context={"job_id":job.id,"title":job.title,"company":job.company,"role_family":job.role_family,"description":job.description,"requirements":job.requirements,"preferred_qualifications":job.preferred_qualifications,"deterministic_score":deterministic,"career_transition_notes":job.career_transition_notes,"preferences":context_snapshot.preferences.model_dump(mode="json"),"evidence":evidence}
            report,response=self.llm.generate_structured(SYSTEM,json.dumps(context),SemanticFitReport);valid_ids={x["id"] for x in evidence};approved=[];unsupported=list(report.unsupported_claims)
            for strength in report.strengths:
                strength.evidence_ids=[x for x in strength.evidence_ids if x in valid_ids]
                result=self.validator.validate(ClaimValidationRequest(generated_claim=strength.statement,supporting_evidence_ids=strength.evidence_ids))
                if result.support_status=="supported":approved.append(strength)
                else:unsupported.append(strength.statement);report.gaps.append(f"Unverified semantic claim removed: {strength.statement}")
            report.job_id=job_id;report.strengths=approved;report.gaps,contradicted_gaps=self.validator.filter_contradicted_gaps(report.gaps);report.requirement_gaps,contradicted_requirement_gaps=self.validator.filter_contradicted_gaps(report.requirement_gaps)
            if any("academic credentials" in gap.lower() and "publication" in gap.lower() for gap in contradicted_gaps):report.gaps.append("No verified publication record or duration of research experience is supplied.")
            unsupported.extend(f"Contradicted gap removed: {gap}" for gap in [*contradicted_gaps,*contradicted_requirement_gaps]);report.unsupported_claims=sorted(set(unsupported));report.evidence_ids=sorted({x for s in approved for x in s.evidence_ids});report.requires_human_review=bool(report.unsupported_claims);report.deterministic_score=deterministic
            if deterministic is not None:report.blended_score=round(deterministic*self.settings.blend_deterministic_weight+report.semantic_fit_score*self.settings.blend_semantic_weight,1)
            report.provider=response.provider;report.model=response.model;report.prompt_version=VERSION;report.latency_ms=response.latency_ms+tool_latency;report.input_tokens=response.usage.input_tokens+(tool_usage.input_tokens if tool_usage else 0);report.output_tokens=response.usage.output_tokens+(tool_usage.output_tokens if tool_usage else 0);report.cached_tokens=response.usage.cached_tokens+(tool_usage.cached_tokens if tool_usage else 0);report.estimated_cost=response.usage.estimated_cost+(tool_usage.estimated_cost if tool_usage else 0)
            assert_current(context_snapshot)
            context_snapshot.validate_evidence(report.evidence_ids)
            saved=cached or SemanticAnalysisRecord(job_id=job_id,fingerprint=fingerprint,**context_snapshot.ownership());saved.deterministic_score=deterministic;saved.semantic_score=report.semantic_fit_score;saved.blended_score=report.blended_score;saved.report_json={**report.model_dump(mode="json"),"job_version":job_version(record)};saved.provider=report.provider;saved.model=report.model;saved.prompt_version=VERSION;saved.evidence_version=version;saved.input_tokens=report.input_tokens;saved.output_tokens=report.output_tokens;saved.cached_tokens=report.cached_tokens;saved.estimated_cost=report.estimated_cost;saved.latency_ms=report.latency_ms;saved.created_at=datetime.now(timezone.utc);db.add(saved);db.commit();db.expire(record,["semantic_analyses"])
            evaluation = self.jobs.evaluation(db, job_id, context_snapshot)
            if evaluation:
                evaluation.opportunity_score = self.jobs.to_schema(record, context=context_snapshot).opportunity_score.overall_score
                db.commit()
            actions=[{"step":1,"tool":"get_deterministic_score","status":"completed"},*[{**action,"step":index+2} for index,action in enumerate(tool_actions)],{"step":len(tool_actions)+2,"tool":"generate_structured_fit","status":"completed"},{"step":len(tool_actions)+3,"tool":"validate_claims","status":"completed","approved_strengths":len(approved)},{"step":len(tool_actions)+4,"tool":"validate_gaps","status":"completed","contradictions_removed":len(contradicted_gaps)+len(contradicted_requirement_gaps)}]
            self.runs.complete(db,run,report.model_dump(mode="json"),actions,evidence_ids_used=report.evidence_ids,input_tokens=report.input_tokens,output_tokens=report.output_tokens,cached_tokens=report.cached_tokens,estimated_cost=report.estimated_cost,latency_ms=report.latency_ms,requires_human_review=report.requires_human_review)
            return AnalysisResponse(status="completed",report=report,deterministic_score=deterministic,agent_run_id=run.id)
        except Exception as exc:
            self.runs.fail(db,run,str(exc));return AnalysisResponse(status="fallback_deterministic",deterministic_score=deterministic,error=str(exc),agent_run_id=run.id)
