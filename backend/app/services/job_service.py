from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ApplicationEventRecord, ApplicationRecord, JobRecord, JobScoreRecord
from app.models.application import ApplicationStatus
from app.models.job import Job, JobList, ScoreResult
from app.services.dedupe_service import canonicalize_url, normalize_text
from app.services.normalization_service import description_fingerprint,normalize_company,normalize_location
from app.models.role_family import FamilyFitResult,RoleFamilyClassification
from app.services.opportunity_service import OpportunityScoringService
from app.services.profile_service import load_preferences
from app.core.config import get_settings


class JobService:
    def to_schema(self, record: JobRecord, preferences=None) -> Job:
        latest = max(record.scores, key=lambda score: score.created_at) if record.scores else None
        semantic=max(record.semantic_analyses,key=lambda item:item.created_at) if record.semantic_analyses else None
        report=semantic.report_json if semantic else None
        job=Job(id=record.id, external_id=record.external_id, source=record.source, company=record.company, title=record.title, location=record.location, remote_type=record.remote_type, employment_type=record.employment_type, salary_min=record.salary_min, salary_max=record.salary_max, salary_currency=record.salary_currency, description=record.description, requirements=record.requirements or [], preferred_qualifications=record.preferred_qualifications or [], apply_url=record.apply_url, source_url=record.source_url, posted_at=record.posted_at, discovered_at=record.discovered_at, fit_score=record.family_fit_score if record.family_fit_score is not None else latest.overall_score if latest else None, fit_explanation=latest.reasoning_summary if latest else None, matched_skills=latest.matched_skills if latest else [], missing_skills=latest.missing_skills if latest else [], recommendation=record.family_recommendation if record.family_recommendation else latest.recommendation if latest else None, application_status=record.application.status if record.application else "discovered", component_scores=latest.component_scores if latest else {}, strengths=record.family_strengths or (latest.strengths if latest else []), gaps=record.family_gaps or (latest.gaps if latest else []), human_label=record.feedback.human_label if record.feedback else None, human_notes=record.feedback.human_notes if record.feedback else None,role_family=record.feedback.human_role_family if record.feedback and record.feedback.human_role_family else record.role_family or "UNKNOWN",role_family_confidence=record.role_family_confidence or 0,role_family_reasons=record.role_family_reasons or [],classification_method="human_override" if record.feedback and record.feedback.human_role_family else record.classification_method or "deterministic_rules",deterministic_family=record.deterministic_family,deterministic_confidence=record.deterministic_confidence,semantic_family=record.semantic_family,semantic_confidence=record.semantic_confidence,final_family=record.final_family,classification_resolution_method=record.classification_resolution_method,family_fit_score=record.family_fit_score,family_component_scores=record.family_component_scores or {},matched_evidence_ids=record.matched_evidence_ids or [],career_transition_flag=record.career_transition_flag or False,career_transition_notes=record.career_transition_notes,raw_company=record.raw_company,canonical_company=record.canonical_company,normalized_location=record.normalized_location,alternate_sources=record.alternate_sources or [],semantic_fit_score=semantic.semantic_score if semantic else None,semantic_fit_confidence=(report or {}).get("confidence") if semantic else None,semantic_analysis_status="COMPLETE" if semantic else "NOT_ANALYZED",semantic_provider=semantic.provider if semantic else None,semantic_model=semantic.model if semantic else None,semantic_estimated_cost=semantic.estimated_cost if semantic else 0)
        job.opportunity_score=OpportunityScoringService().score(job,preferences or load_preferences(),report);return job

    def list(self, db: Session, recommendation: str | None = None, limit: int = 100, offset: int = 0, role_family:str|None=None,source:str|None=None,company:str|None=None,location:str|None=None,human_label:str|None=None,diversified:bool=True) -> JobList:
        records = db.scalars(select(JobRecord).options(selectinload(JobRecord.scores), selectinload(JobRecord.application), selectinload(JobRecord.feedback),selectinload(JobRecord.semantic_analyses))).all()
        preferences=load_preferences();jobs = [self.to_schema(item,preferences) for item in records if item.posting_status != "CLOSED"]
        if role_family: jobs=[job for job in jobs if job.role_family==role_family]
        if source: jobs=[job for job in jobs if job.source==source]
        if company: jobs=[job for job in jobs if company.lower() in job.company.lower()]
        if location: jobs=[job for job in jobs if location.lower() in (job.location or "").lower()]
        if human_label: jobs=[job for job in jobs if job.human_label==human_label]
        if recommendation == "skipped": jobs = [job for job in jobs if job.application_status == "skipped"]
        elif recommendation: jobs = [job for job in jobs if job.recommendation == recommendation]
        jobs.sort(key=lambda job:(-(job.opportunity_score.overall_score if job.opportunity_score else -1),-(job.opportunity_score.freshness_score if job.opportunity_score and job.opportunity_score.freshness_score is not None else -1),job.id or 0))
        raw_jobs=list(jobs)
        if diversified:
            cap=max(1,get_settings().dashboard_max_jobs_per_company);company_counts={};jobs=[]
            for job in raw_jobs:
                key=job.company.casefold()
                if company_counts.get(key,0)>=cap:continue
                jobs.append(job);company_counts[key]=company_counts.get(key,0)+1
        counts = {"scanned": len(records), "raw_total":len(raw_jobs),"companies":len({job.company.casefold() for job in raw_jobs}),"passing_filters": sum((job.fit_score or 0) >= 60 for job in raw_jobs), "strong": sum(job.opportunity_score and job.opportunity_score.overall_score>=75 for job in raw_jobs), "exceptional": sum(job.opportunity_score and job.opportunity_score.overall_score>=90 for job in raw_jobs), "ready": sum(job.application_status == "ready_for_review" for job in raw_jobs)}
        return JobList(items=jobs[offset:offset + limit], total=len(jobs), counts=counts)

    def get(self, db: Session, job_id: int) -> JobRecord | None:
        return db.scalar(select(JobRecord).where(JobRecord.id == job_id).options(selectinload(JobRecord.scores), selectinload(JobRecord.application), selectinload(JobRecord.feedback),selectinload(JobRecord.semantic_analyses)))

    def create(self, db: Session, job: Job) -> JobRecord:
        data = job.model_dump(exclude={"id", "fit_score", "fit_explanation", "matched_skills", "missing_skills", "recommendation", "application_status", "component_scores", "strengths", "gaps", "human_label", "human_notes","opportunity_score","semantic_fit_score","semantic_fit_confidence","semantic_analysis_status","semantic_provider","semantic_model","semantic_estimated_cost"}, mode="python")
        data["apply_url"] = str(job.apply_url); data["source_url"] = str(job.source_url); data["normalized_title"] = normalize_text(job.title); data["canonical_apply_url"] = canonicalize_url(str(job.apply_url))
        data["raw_company"]=job.company; data["canonical_company"]=normalize_company(job.company); data["normalized_location"]=normalize_location(job.location,job.remote_type.value); data["description_fingerprint"]=description_fingerprint(job.description)
        record = JobRecord(**data); db.add(record); db.flush(); application = ApplicationRecord(job_id=record.id, status=ApplicationStatus.discovered); db.add(application); db.flush(); db.add(ApplicationEventRecord(application_id=application.id, to_status=ApplicationStatus.discovered, note="Job discovered")); db.commit(); db.refresh(record); return record

    def save_score(self, db: Session, job_id: int, result: ScoreResult) -> None:
        db.add(JobScoreRecord(job_id=job_id, overall_score=result.overall_score, component_scores={key: value.model_dump() for key, value in result.component_scores.items()}, strengths=result.strengths, gaps=result.gaps, matched_skills=result.matched_skills, missing_skills=result.missing_skills, reasoning_summary=result.reasoning_summary, recommendation=result.recommendation)); db.commit()

    def save_family_fit(self,db:Session,job_id:int,classification:RoleFamilyClassification,result:FamilyFitResult)->None:
        record=db.get(JobRecord,job_id); record.role_family=classification.role_family; record.role_family_confidence=classification.confidence; record.role_family_reasons=classification.reasons; record.classification_method=classification.classification_method;record.deterministic_family=classification.role_family;record.deterministic_confidence=classification.confidence;record.final_family=classification.role_family;record.classification_resolution_method="deterministic_precedence"; record.family_fit_score=result.family_fit_score; record.family_component_scores=result.family_component_scores;record.family_recommendation=result.recommendation;record.family_strengths=result.strengths;record.family_gaps=result.gaps; record.matched_evidence_ids=result.matched_evidence_ids; record.career_transition_flag=result.career_transition_flag; record.career_transition_notes=result.career_transition_notes; db.commit()

    def set_status(self, db: Session, job_id: int, status: ApplicationStatus) -> ApplicationRecord | None:
        application = db.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id == job_id))
        if not application: return None
        previous = application.status; application.status = status; db.add(ApplicationEventRecord(application_id=application.id, from_status=previous, to_status=status, note=f"Status changed to {status}")); db.commit(); db.refresh(application); return application
