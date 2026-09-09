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
from app.services.posting_confidence_service import posting_confidence
from app.services.candidate_context_service import current_context, assert_current, job_version


class JobPersistenceError(RuntimeError):
    """A single provider job could not be persisted safely."""

    def __init__(self, job: Job, cause: Exception):
        super().__init__(f"{type(cause).__name__} while persisting provider job")
        self.source = job.source
        self.external_id = job.external_id
        self.cause_type = type(cause).__name__


class JobService:
    def to_schema(self, record: JobRecord, preferences=None, context=None) -> Job:
        context = context or current_context()
        valid = [score for score in record.scores if not context.pending and score.candidate_context_key == context.key
                 and score.job_version == job_version(record) and set(score.matched_evidence_ids or []).issubset(context.evidence_ids)]
        latest = max(valid, key=lambda score: score.created_at) if valid else None
        analyses = [item for item in record.semantic_analyses if not context.pending and item.candidate_context_key == context.key
                    and item.report_json.get("job_version") == job_version(record)
                    and set(item.report_json.get("evidence_ids", [])).issubset(context.evidence_ids)
                    and all(set(x.get("evidence_ids", [])).issubset(context.evidence_ids) for x in item.report_json.get("strengths", []) if isinstance(x, dict))]
        semantic=max(analyses,key=lambda item:item.created_at) if analyses else None
        if record.application and record.application.candidate_profile_id != context.profile_id:
            from sqlalchemy.orm import attributes
            attributes.set_committed_value(record, "application", None)
        if record.feedback and record.feedback.candidate_profile_id != context.profile_id:
            from sqlalchemy.orm import attributes
            attributes.set_committed_value(record, "feedback", None)
        report=semantic.report_json if semantic else None
        job=Job(id=record.id, external_id=record.external_id, source=record.source, company=record.company, title=record.title, location=record.location, remote_type=record.remote_type, employment_type=record.employment_type, salary_min=record.salary_min, salary_max=record.salary_max, salary_currency=record.salary_currency, description=record.description, requirements=record.requirements or [], preferred_qualifications=record.preferred_qualifications or [], apply_url=record.apply_url, source_url=record.source_url, posted_at=record.posted_at, discovered_at=record.discovered_at, fit_score=(latest.family_fit_score if latest else None) if (latest.family_fit_score if latest else None) is not None else latest.overall_score if latest else None, fit_explanation=latest.reasoning_summary if latest else None, matched_skills=latest.matched_skills if latest else [], missing_skills=latest.missing_skills if latest else [], recommendation=(latest.family_recommendation if latest else None) if (latest.family_recommendation if latest else None) else latest.recommendation if latest else None, application_status=record.application.status if record.application else "discovered", component_scores=latest.component_scores if latest else {}, strengths=(latest.family_strengths if latest else []) or (latest.strengths if latest else []), gaps=(latest.family_gaps if latest else []) or (latest.gaps if latest else []), human_label=record.feedback.human_label if record.feedback else None, human_notes=record.feedback.human_notes if record.feedback else None,role_family=record.feedback.human_role_family if record.feedback and record.feedback.human_role_family else record.role_family or "UNKNOWN",role_family_confidence=record.role_family_confidence or 0,role_family_reasons=record.role_family_reasons or [],classification_method="human_override" if record.feedback and record.feedback.human_role_family else record.classification_method or "deterministic_rules",deterministic_family=record.deterministic_family,deterministic_confidence=record.deterministic_confidence,semantic_family=record.semantic_family,semantic_confidence=record.semantic_confidence,final_family=record.final_family,classification_resolution_method=record.classification_resolution_method,family_fit_score=(latest.family_fit_score if latest else None),family_component_scores=(latest.family_component_scores if latest else {}) or {},matched_evidence_ids=(latest.matched_evidence_ids if latest else []) or [],career_transition_flag=(latest.career_transition_flag if latest else False) or False,career_transition_notes=(latest.career_transition_notes if latest else None),raw_company=record.raw_company,canonical_company=record.canonical_company,normalized_location=record.normalized_location,alternate_sources=record.alternate_sources or [],semantic_fit_score=semantic.semantic_score if semantic else None,semantic_fit_confidence=(report or {}).get("confidence") if semantic else None,semantic_analysis_status="COMPLETE" if semantic else "NOT_ANALYZED",semantic_provider=semantic.provider if semantic else None,semantic_model=semantic.model if semantic else None,semantic_estimated_cost=semantic.estimated_cost if semantic else 0,first_seen_at=record.first_seen_at,last_seen_at=record.last_seen_at,last_verified_at=record.last_verified_at,posting_status=record.posting_status)
        job.opportunity_score=OpportunityScoringService().score(job,preferences or context.preferences,report)
        confidence=posting_confidence(job);job.posting_confidence=confidence["level"];job.posting_confidence_reason=confidence["reason"]
        return job

    def list(self, db: Session, recommendation: str | None = None, limit: int = 100, offset: int = 0, role_family:str|None=None,source:str|None=None,company:str|None=None,location:str|None=None,human_label:str|None=None,diversified:bool=False) -> JobList:
        records = db.scalars(select(JobRecord).options(selectinload(JobRecord.scores), selectinload(JobRecord.application), selectinload(JobRecord.feedback),selectinload(JobRecord.semantic_analyses))).all()
        context=current_context();preferences=context.preferences;jobs=[self.to_schema(item,preferences,context) for item in records if item.posting_status not in {"CLOSED","EXPIRED","NOT_FOUND"}]
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
            has_explicit_filter=any((recommendation,role_family,source,company,location,human_label))
            # Newly discovered jobs must remain visible until they have actually
            # been scored. A default low-confidence OpportunityScore is not a
            # user decision to hide an otherwise valid posting.
            eligible=raw_jobs if has_explicit_filter else [job for job in raw_jobs if job.fit_score is None or (job.opportunity_score and job.opportunity_score.recommendation.value not in {"STRETCH","SKIP"})]
            for job in eligible:
                key=job.company.casefold()
                if company_counts.get(key,0)>=cap:continue
                jobs.append(job);company_counts[key]=company_counts.get(key,0)+1
        counts = {"scanned": len(records), "raw_total":len(raw_jobs),"companies":len({job.company.casefold() for job in raw_jobs}),"passing_filters": sum((job.fit_score or 0) >= 60 for job in raw_jobs), "strong": sum(job.opportunity_score and job.opportunity_score.overall_score>=75 for job in raw_jobs), "exceptional": sum(job.opportunity_score and job.opportunity_score.overall_score>=90 for job in raw_jobs), "ready": sum(job.application_status == "ready_for_review" for job in raw_jobs)}
        return JobList(items=jobs[offset:offset + limit], total=len(jobs), counts=counts)

    def get(self, db: Session, job_id: int) -> JobRecord | None:
        return db.scalar(select(JobRecord).where(JobRecord.id == job_id).options(selectinload(JobRecord.scores), selectinload(JobRecord.application), selectinload(JobRecord.feedback),selectinload(JobRecord.semantic_analyses)))

    def create(self, db: Session, job: Job) -> JobRecord:
        data = job.model_dump(exclude={"id", "fit_score", "fit_explanation", "matched_skills", "missing_skills", "recommendation", "application_status", "component_scores", "strengths", "gaps", "human_label", "human_notes","opportunity_score","semantic_fit_score","semantic_fit_confidence","semantic_analysis_status","semantic_provider","semantic_model","semantic_estimated_cost","first_seen_at","last_seen_at","last_verified_at","posting_status","posting_confidence","posting_confidence_reason"}, mode="python")
        data = {key: value for key, value in data.items() if key in JobRecord.__table__.columns}
        data["apply_url"] = str(job.apply_url); data["source_url"] = str(job.source_url); data["normalized_title"] = normalize_text(job.title); data["canonical_apply_url"] = canonicalize_url(str(job.apply_url))
        data["raw_company"]=job.company; data["canonical_company"]=normalize_company(job.company); data["normalized_location"]=normalize_location(job.location,job.remote_type.value); data["description_fingerprint"]=description_fingerprint(job.description)
        try:
            record = JobRecord(**data); db.add(record); db.flush(); application = ApplicationRecord(job_id=record.id, status=ApplicationStatus.discovered); db.add(application); db.flush(); db.add(ApplicationEventRecord(application_id=application.id, to_status=ApplicationStatus.discovered, note="Job discovered")); db.commit(); db.refresh(record); return record
        except Exception as exc:
            db.rollback()
            raise JobPersistenceError(job, exc) from exc

    def evaluation(self, db, job_id, context=None):
        context = context or current_context()
        return db.scalar(select(JobScoreRecord).where(JobScoreRecord.job_id == job_id,
                         JobScoreRecord.candidate_context_key == context.key))

    def save_score(self, db: Session, job_id: int, result: ScoreResult, context=None) -> None:
        context = context or current_context()
        assert_current(context)
        row = self.evaluation(db, job_id, context)
        if row is None:
            row = JobScoreRecord(job_id=job_id, **context.ownership())
            db.add(row)
        row.job_version = job_version(db.get(JobRecord, job_id))
        row.overall_score = result.overall_score
        row.component_scores = {key: value.model_dump() for key, value in result.component_scores.items()}
        row.strengths = result.strengths
        row.gaps = result.gaps
        row.matched_skills = result.matched_skills
        row.missing_skills = result.missing_skills
        row.reasoning_summary = result.reasoning_summary
        row.recommendation = result.recommendation
        db.commit()
        db.expire(db.get(JobRecord, job_id), ["scores"])

    def save_family_fit(self, db: Session, job_id: int, classification: RoleFamilyClassification,
                        result: FamilyFitResult, context=None) -> None:
        context = context or current_context()
        assert_current(context)
        context.validate_evidence(result.matched_evidence_ids)
        record = db.get(JobRecord, job_id)
        row = self.evaluation(db, job_id, context)
        if row is None:
            raise ValueError("Deterministic candidate evaluation must precede family scoring")
        record.role_family = classification.role_family
        record.role_family_confidence = classification.confidence
        record.role_family_reasons = classification.reasons
        record.classification_method = classification.classification_method
        record.deterministic_family = classification.role_family
        record.deterministic_confidence = classification.confidence
        record.final_family = classification.role_family
        record.classification_resolution_method = "deterministic_precedence"
        row.family_fit_score = result.family_fit_score
        row.family_component_scores = result.family_component_scores
        row.family_recommendation = result.recommendation
        row.family_strengths = result.strengths
        row.family_gaps = result.gaps
        row.matched_evidence_ids = result.matched_evidence_ids
        row.career_transition_flag = result.career_transition_flag
        row.career_transition_notes = result.career_transition_notes
        db.commit()
        db.expire(record, ["scores"])
        schema = self.to_schema(record, context=context)
        row.opportunity_score = schema.opportunity_score.overall_score
        row.constraint_results = schema.opportunity_score.constraints.model_dump(mode="json")
        db.commit()

    def evaluate_catalog(self, db, context=None):
        from app.services.evidence_service import EvidenceService
        from app.services.scoring_service import DeterministicScoringEngine
        from app.services.family_scoring_service import FamilyScoringEngine
        from app.services.role_family_service import DeterministicRoleFamilyClassifier
        context = context or current_context()
        if context.pending:
            raise ValueError("Approve the replacement resume and review preferences before finding jobs")
        assert_current(context)
        classifier = DeterministicRoleFamilyClassifier()
        family = FamilyScoringEngine(EvidenceService(records=context.evidence))
        scorer = DeterministicScoringEngine()
        count = 0
        records = db.scalars(select(JobRecord).options(selectinload(JobRecord.scores), selectinload(JobRecord.semantic_analyses),
                            selectinload(JobRecord.application), selectinload(JobRecord.feedback))).all()
        for record in records:
            if record.posting_status in {"CLOSED", "EXPIRED", "NOT_FOUND"}: continue
            row = next((x for x in record.scores if x.candidate_context_key == context.key), None)
            if row and row.job_version == job_version(record) and row.family_fit_score is not None: continue
            job = self.to_schema(record, context=context)
            classification = classifier.classify(job)
            job.role_family = classification.role_family
            self.save_score(db, record.id, scorer.score(job, context.profile, context.preferences), context)
            self.save_family_fit(db, record.id, classification, family.score(job, context.profile, context.preferences), context)
            count += 1
        return count

    def set_status(self, db: Session, job_id: int, status: ApplicationStatus) -> ApplicationRecord | None:
        application = db.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id == job_id))
        if not application:
            if db.get(JobRecord, job_id) is None: return None
            application = ApplicationRecord(job_id=job_id, status=ApplicationStatus.discovered)
            db.add(application)
            db.flush()
        previous = application.status; application.status = status; db.add(ApplicationEventRecord(application_id=application.id, from_status=previous, to_status=status, note=f"Status changed to {status}")); db.commit(); db.refresh(application); return application
