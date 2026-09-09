from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CandidateOwned:
    """Application history belongs to a candidate, across that candidate's edits."""
    candidate_profile_id: Mapped[str | None] = mapped_column(String(80), index=True)


class EvaluationOwned(CandidateOwned):
    candidate_profile_version: Mapped[int | None] = mapped_column(Integer)
    preference_version: Mapped[str | None] = mapped_column(String(64))
    candidate_context_key: Mapped[str | None] = mapped_column(String(64), index=True)


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(Text, index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    company: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text, index=True)
    normalized_title: Mapped[str] = mapped_column(Text, index=True)
    location: Mapped[str | None] = mapped_column(Text)
    remote_type: Mapped[str] = mapped_column(String(30), default="unspecified")
    employment_type: Mapped[str | None] = mapped_column(String(100))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[list[str]] = mapped_column(JSON, default=list)
    preferred_qualifications: Mapped[list[str]] = mapped_column(JSON, default=list)
    apply_url: Mapped[str] = mapped_column(Text)
    canonical_apply_url: Mapped[str] = mapped_column(Text, index=True)
    source_url: Mapped[str] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    role_family:Mapped[str]=mapped_column(String(40),default="UNKNOWN",index=True)
    role_family_confidence:Mapped[float]=mapped_column(Float,default=0)
    role_family_reasons:Mapped[list[str]]=mapped_column(JSON,default=list)
    classification_method:Mapped[str]=mapped_column(String(40),default="deterministic_rules")
    deterministic_family:Mapped[str|None]=mapped_column(String(40));deterministic_confidence:Mapped[float|None]=mapped_column(Float);semantic_family:Mapped[str|None]=mapped_column(String(40));semantic_confidence:Mapped[float|None]=mapped_column(Float);final_family:Mapped[str|None]=mapped_column(String(40));classification_resolution_method:Mapped[str|None]=mapped_column(String(60))
    raw_company:Mapped[str|None]=mapped_column(Text)
    canonical_company:Mapped[str|None]=mapped_column(Text,index=True)
    normalized_location:Mapped[str|None]=mapped_column(Text,index=True)
    description_fingerprint:Mapped[str|None]=mapped_column(String(64),index=True)
    alternate_sources:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
    first_seen_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    last_seen_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    last_verified_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    posting_status:Mapped[str]=mapped_column(String(30),default="UNKNOWN",index=True)

    scores: Mapped[list["JobScoreRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    application: Mapped["ApplicationRecord | None"] = relationship(back_populates="job", uselist=False)
    feedback: Mapped["JobFeedbackRecord | None"] = relationship(back_populates="job", uselist=False)
    semantic_analyses: Mapped[list["SemanticAnalysisRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobScoreRecord(EvaluationOwned, Base):
    __tablename__ = "job_scores"
    __table_args__ = (UniqueConstraint("candidate_context_key", "job_id", name="uq_candidate_job_evaluation"),)
    job_version: Mapped[str | None] = mapped_column(String(64))
    opportunity_score: Mapped[float | None] = mapped_column(Float)
    constraint_results: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    family_fit_score:Mapped[float|None]=mapped_column(Float)
    family_component_scores:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)
    family_recommendation:Mapped[str|None]=mapped_column(String(30))
    family_strengths:Mapped[list[str]]=mapped_column(JSON,default=list)
    family_gaps:Mapped[list[str]]=mapped_column(JSON,default=list)
    matched_evidence_ids:Mapped[list[str]]=mapped_column(JSON,default=list)
    career_transition_flag:Mapped[bool]=mapped_column(default=False)
    career_transition_notes:Mapped[str|None]=mapped_column(Text)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    scorer_version: Mapped[str] = mapped_column(String(50), default="deterministic-v1")
    overall_score: Mapped[float] = mapped_column(Float)
    component_scores: Mapped[dict[str, Any]] = mapped_column(JSON)
    strengths: Mapped[list[str]] = mapped_column(JSON)
    gaps: Mapped[list[str]] = mapped_column(JSON)
    matched_skills: Mapped[list[str]] = mapped_column(JSON)
    missing_skills: Mapped[list[str]] = mapped_column(JSON)
    reasoning_summary: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    job: Mapped[JobRecord] = relationship(back_populates="scores")


class ApplicationRecord(CandidateOwned, Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "job_id", name="uq_applicationrecord_candidate_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"),  index=True)
    status: Mapped[str] = mapped_column(String(40), default="discovered", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[JobRecord] = relationship(back_populates="application")
    events: Mapped[list["ApplicationEventRecord"]] = relationship(back_populates="application", cascade="all, delete-orphan")


class ApplicationEventRecord(CandidateOwned, Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    application: Mapped[ApplicationRecord] = relationship(back_populates="events")


class JobSourceRecord(Base):
    __tablename__="job_sources"
    id:Mapped[int]=mapped_column(primary_key=True)
    company:Mapped[str]=mapped_column(String(255),index=True)
    ats_type:Mapped[str]=mapped_column(String(40),index=True)
    board_identifier:Mapped[str]=mapped_column(String(255))
    careers_url:Mapped[str|None]=mapped_column(Text)
    enabled:Mapped[bool]=mapped_column(default=True,index=True)
    scan_frequency:Mapped[str]=mapped_column(String(50),default="manual")
    last_scanned_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_success_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_error:Mapped[str|None]=mapped_column(Text)
    jobs_discovered_total:Mapped[int]=mapped_column(Integer,default=0)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    company_id:Mapped[int|None]=mapped_column(ForeignKey("companies.id"),index=True)
    priority:Mapped[str]=mapped_column(String(20),default="NORMAL")
    configuration:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)
    last_attempt_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));last_failure_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));failure_type:Mapped[str|None]=mapped_column(String(40));consecutive_failures:Mapped[int]=mapped_column(Integer,default=0);average_latency_ms:Mapped[float|None]=mapped_column(Float);last_job_count:Mapped[int]=mapped_column(Integer,default=0);retry_after:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));health_status:Mapped[str]=mapped_column(String(40),default="UNKNOWN",index=True);disabled_reason:Mapped[str|None]=mapped_column(Text)


class ScanRunRecord(Base):
    __tablename__="scan_runs"
    id:Mapped[int]=mapped_column(primary_key=True)
    started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    status:Mapped[str]=mapped_column(String(40),default="queued",index=True)
    source_count:Mapped[int]=mapped_column(Integer,default=0); successful_source_count:Mapped[int]=mapped_column(Integer,default=0); failed_source_count:Mapped[int]=mapped_column(Integer,default=0)
    jobs_fetched:Mapped[int]=mapped_column(Integer,default=0); jobs_filtered:Mapped[int]=mapped_column(Integer,default=0); jobs_deduplicated:Mapped[int]=mapped_column(Integer,default=0); jobs_added:Mapped[int]=mapped_column(Integer,default=0); jobs_updated:Mapped[int]=mapped_column(Integer,default=0); jobs_scored:Mapped[int]=mapped_column(Integer,default=0)
    exceptional_count:Mapped[int]=mapped_column(Integer,default=0); strong_count:Mapped[int]=mapped_column(Integer,default=0); possible_count:Mapped[int]=mapped_column(Integer,default=0); weak_count:Mapped[int]=mapped_column(Integer,default=0); skip_count:Mapped[int]=mapped_column(Integer,default=0)
    errors_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); duration_seconds:Mapped[float|None]=mapped_column(Float)
    jobs_by_source_type:Mapped[dict[str,int]]=mapped_column(JSON,default=dict); jobs_by_role_family:Mapped[dict[str,int]]=mapped_column(JSON,default=dict); duplicates_across_sources:Mapped[int]=mapped_column(Integer,default=0); source_detection_failures:Mapped[int]=mapped_column(Integer,default=0)


class JobFeedbackRecord(CandidateOwned, Base):
    __tablename__="job_feedback"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "job_id", name="uq_jobfeedbackrecord_candidate_job"),)
    id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True)
    human_label:Mapped[str]=mapped_column(String(20)); human_notes:Mapped[str|None]=mapped_column(Text)
    labeled_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    job:Mapped[JobRecord]=relationship(back_populates="feedback")
    human_role_family:Mapped[str|None]=mapped_column(String(40))


class CompanyRecord(Base):
    __tablename__="companies"
    id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(255)); canonical_name:Mapped[str]=mapped_column(String(255),unique=True,index=True)
    website_url:Mapped[str|None]=mapped_column(Text); careers_url:Mapped[str|None]=mapped_column(Text); company_type:Mapped[str]=mapped_column(String(40),default="OTHER"); priority:Mapped[str]=mapped_column(String(20),default="NORMAL"); enabled:Mapped[bool]=mapped_column(default=True); notes:Mapped[str|None]=mapped_column(Text); detected_ats:Mapped[str|None]=mapped_column(String(50)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)


class AgentRunRecord(EvaluationOwned, Base):
    __tablename__="agent_runs"
    id:Mapped[int]=mapped_column(primary_key=True); agent_type:Mapped[str]=mapped_column(String(40),index=True); objective:Mapped[str]=mapped_column(Text); job_id:Mapped[int|None]=mapped_column(ForeignKey("jobs.id")); status:Mapped[str]=mapped_column(String(40),default="queued",index=True)
    started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    input_state_json:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict); output_state_json:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict); actions_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); errors_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); requires_human_review:Mapped[bool]=mapped_column(default=False)
    provider:Mapped[str|None]=mapped_column(String(40)); model:Mapped[str|None]=mapped_column(String(120)); prompt_version:Mapped[str|None]=mapped_column(String(80)); temperature:Mapped[float|None]=mapped_column(Float)
    evidence_ids_used:Mapped[list[str]]=mapped_column(JSON,default=list); sources_used:Mapped[list[str]]=mapped_column(JSON,default=list); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); cached_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0)


class EvidenceEmbeddingRecord(EvaluationOwned, Base):
    __tablename__="evidence_embeddings"
    id:Mapped[int]=mapped_column(primary_key=True); evidence_id:Mapped[str]=mapped_column(String(80),index=True); evidence_version:Mapped[str]=mapped_column(String(64),index=True); provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); embedding_version:Mapped[str]=mapped_column(String(80)); vector:Mapped[list[float]]=mapped_column(JSON); generated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint("evidence_id","evidence_version","provider","model",name="uq_evidence_embedding_version"),)


class SemanticAnalysisRecord(EvaluationOwned, Base):
    __tablename__="semantic_analyses"
    id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True); fingerprint:Mapped[str]=mapped_column(String(64),unique=True,index=True); deterministic_score:Mapped[float|None]=mapped_column(Float); semantic_score:Mapped[float]=mapped_column(Float); blended_score:Mapped[float|None]=mapped_column(Float); report_json:Mapped[dict[str,Any]]=mapped_column(JSON); provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); prompt_version:Mapped[str]=mapped_column(String(80)); evidence_version:Mapped[str]=mapped_column(String(64)); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); cached_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    job:Mapped[JobRecord]=relationship(back_populates="semantic_analyses")


class CompanyResearchRecord(EvaluationOwned, Base):
    __tablename__="company_research"
    id:Mapped[int]=mapped_column(primary_key=True); company_id:Mapped[int|None]=mapped_column(ForeignKey("companies.id"),index=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True); fingerprint:Mapped[str]=mapped_column(String(64),unique=True,index=True); summary:Mapped[str]=mapped_column(Text); technical_focus:Mapped[list[str]]=mapped_column(JSON,default=list); research_areas:Mapped[list[str]]=mapped_column(JSON,default=list); products:Mapped[list[str]]=mapped_column(JSON,default=list); role_context:Mapped[str]=mapped_column(Text,default=""); relevant_teams:Mapped[list[str]]=mapped_column(JSON,default=list); culture_signals:Mapped[list[str]]=mapped_column(JSON,default=list); hiring_signals:Mapped[list[str]]=mapped_column(JSON,default=list); sources:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); report_json:Mapped[dict[str,Any]]=mapped_column(JSON); generated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); prompt_version:Mapped[str]=mapped_column(String(80)); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); cached_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0)


class ApplicationPackageRecord(CandidateOwned, Base):
    __tablename__="application_packages"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "job_id", name="uq_applicationpackagerecord_candidate_job"),)
    id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True); status:Mapped[str]=mapped_column(String(40),default="DRAFT",index=True)
    resume_version_id:Mapped[str]=mapped_column(String(80)); resume_strategy_json:Mapped[dict[str,Any]]=mapped_column(JSON); tailored_resume_path:Mapped[str|None]=mapped_column(Text); tailored_resume_preview_json:Mapped[dict[str,Any]]=mapped_column(JSON); job_requirements_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
    cover_letter:Mapped[str|None]=mapped_column(Text); original_cover_letter:Mapped[str|None]=mapped_column(Text); cover_letter_evidence_ids:Mapped[list[str]]=mapped_column(JSON,default=list); cover_letter_required:Mapped[bool]=mapped_column(default=False); cover_letter_status:Mapped[str]=mapped_column(String(40),default="NOT_GENERATED")
    application_answers_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); application_summary_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
    fit_analysis_id:Mapped[int|None]=mapped_column(ForeignKey("semantic_analyses.id")); research_report_id:Mapped[int|None]=mapped_column(ForeignKey("company_research.id")); evidence_ids_used:Mapped[list[str]]=mapped_column(JSON,default=list); unsupported_claims_removed:Mapped[list[str]]=mapped_column(JSON,default=list); review_findings_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); review_status:Mapped[str|None]=mapped_column(String(40)); requires_human_review:Mapped[bool]=mapped_column(default=True); human_review_reasons:Mapped[list[str]]=mapped_column(JSON,default=list)
    provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); prompt_versions:Mapped[dict[str,str]]=mapped_column(JSON,default=dict); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); cached_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0)
    evidence_version:Mapped[str]=mapped_column(String(64)); job_fingerprint:Mapped[str]=mapped_column(String(64)); package_fingerprint:Mapped[str]=mapped_column(String(64),index=True); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow); approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))


class ApprovedAnswerHistoryRecord(CandidateOwned, Base):
    __tablename__="approved_answer_history"
    id:Mapped[int]=mapped_column(primary_key=True); question_pattern:Mapped[str]=mapped_column(Text); approved_answer:Mapped[str]=mapped_column(Text); category:Mapped[str]=mapped_column(String(60)); job_id:Mapped[int|None]=mapped_column(ForeignKey("jobs.id")); company_context:Mapped[str|None]=mapped_column(String(255)); evidence_ids:Mapped[list[str]]=mapped_column(JSON,default=list); reusable:Mapped[bool]=mapped_column(default=False); approved_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ApplicationFormRecord(CandidateOwned, Base):
    __tablename__="application_forms"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "job_id", name="uq_applicationformrecord_candidate_job"),)
    id:Mapped[int]=mapped_column(primary_key=True);job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);application_url:Mapped[str]=mapped_column(Text);ats:Mapped[str]=mapped_column(String(40));schema_json:Mapped[dict[str,Any]]=mapped_column(JSON);form_fingerprint:Mapped[str]=mapped_column(String(64));status:Mapped[str]=mapped_column(String(40),default="INSPECTED");manual_application_override:Mapped[bool]=mapped_column(default=False);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
class BrowserApplicationEventRecord(CandidateOwned, Base):
    __tablename__="browser_application_events"
    id:Mapped[int]=mapped_column(primary_key=True);job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);event_type:Mapped[str]=mapped_column(String(60),index=True);field_category:Mapped[str|None]=mapped_column(String(60));details_json:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
class ApplicationQueueItemRecord(CandidateOwned, Base):
    __tablename__="application_queue_items"
    id:Mapped[int]=mapped_column(primary_key=True);job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);application_package_id:Mapped[int]=mapped_column(ForeignKey("application_packages.id"));priority:Mapped[float]=mapped_column(Float,default=0);eligibility:Mapped[str]=mapped_column(String(40));status:Mapped[str]=mapped_column(String(40),default="QUEUED",index=True);attempt_count:Mapped[int]=mapped_column(Integer,default=0);next_attempt_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));block_reason:Mapped[str|None]=mapped_column(Text);last_error:Mapped[str|None]=mapped_column(Text);lease_owner:Mapped[str|None]=mapped_column(String(120),index=True);lease_expires_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),index=True);heartbeat_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));submit_started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow);__table_args__=(UniqueConstraint("job_id","application_package_id",name="uq_queue_job_package"),)
class ApplicationReceiptRecord(CandidateOwned, Base):
    __tablename__="application_receipts"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "job_id", name="uq_applicationreceiptrecord_candidate_job"),)
    id:Mapped[int]=mapped_column(primary_key=True);application_id:Mapped[int|None]=mapped_column(ForeignKey("applications.id"));job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);company:Mapped[str]=mapped_column(String(255));role:Mapped[str]=mapped_column(String(255));submitted_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);ats:Mapped[str]=mapped_column(String(40));apply_url:Mapped[str]=mapped_column(Text);confirmation_url:Mapped[str|None]=mapped_column(Text);external_confirmation_text:Mapped[str|None]=mapped_column(Text);external_application_id:Mapped[str|None]=mapped_column(String(255));resume_artifact_hash:Mapped[str]=mapped_column(String(64));application_package_version:Mapped[str]=mapped_column(String(80))

class RuntimeHeartbeatRecord(Base):
    __tablename__="runtime_heartbeats"
    component:Mapped[str]=mapped_column(String(40),primary_key=True);instance_id:Mapped[str]=mapped_column(String(120));status:Mapped[str]=mapped_column(String(40),default="ONLINE");last_heartbeat_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,index=True);last_success_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));details_json:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)

class RuntimeSettingRecord(Base):
    __tablename__="runtime_settings"
    key:Mapped[str]=mapped_column(String(80),primary_key=True);value_json:Mapped[Any]=mapped_column(JSON);updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class MorningReportRecord(CandidateOwned, Base):
    __tablename__="morning_reports"
    id:Mapped[int]=mapped_column(primary_key=True);period_start:Mapped[datetime]=mapped_column(DateTime(timezone=True),index=True);period_end:Mapped[datetime]=mapped_column(DateTime(timezone=True));metrics_json:Mapped[dict[str,Any]]=mapped_column(JSON);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ApplicationOutcomeRecord(CandidateOwned, Base):
    __tablename__="application_outcomes"
    id:Mapped[int]=mapped_column(primary_key=True);job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);application_receipt_id:Mapped[int|None]=mapped_column(ForeignKey("application_receipts.id"));status:Mapped[str]=mapped_column(String(40),index=True);notes:Mapped[str|None]=mapped_column(Text);fit_score:Mapped[float|None]=mapped_column(Float);semantic_score:Mapped[float|None]=mapped_column(Float);role_family:Mapped[str|None]=mapped_column(String(40));company_type:Mapped[str|None]=mapped_column(String(40));resume_version:Mapped[str|None]=mapped_column(String(80));submitted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));recorded_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class JobExclusionRecord(CandidateOwned, Base):
    __tablename__="job_exclusions"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "job_id", name="uq_job_exclusion_candidate_job"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);reason:Mapped[str|None]=mapped_column(Text);created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class DiscoveryLeadRecord(CandidateOwned, Base):
    __tablename__="discovery_leads"
    __table_args__ = (UniqueConstraint("candidate_profile_id", "url", name="uq_discovery_lead_candidate_url"),)
    id:Mapped[int]=mapped_column(primary_key=True);url:Mapped[str]=mapped_column(Text);title:Mapped[str|None]=mapped_column(String(255));company:Mapped[str|None]=mapped_column(String(255));query:Mapped[str]=mapped_column(Text);provider:Mapped[str]=mapped_column(String(40));status:Mapped[str]=mapped_column(String(40),default="UNVERIFIED");created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ContactRecord(CandidateOwned, Base):
    __tablename__="contact_intelligence"
    id:Mapped[int]=mapped_column(primary_key=True);job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True)
    company:Mapped[str]=mapped_column(String(255),index=True);name:Mapped[str]=mapped_column(String(255));current_title:Mapped[str]=mapped_column(String(255));public_profile_url:Mapped[str]=mapped_column(Text);source_type:Mapped[str]=mapped_column(String(60));source_url:Mapped[str]=mapped_column(Text)
    team:Mapped[str|None]=mapped_column(String(255));domains:Mapped[list[str]]=mapped_column(JSON,default=list);location:Mapped[str|None]=mapped_column(String(255));recruiting_relevance:Mapped[bool]=mapped_column(default=False);direct_function_ownership:Mapped[bool]=mapped_column(default=False);company_is_small:Mapped[bool]=mapped_column(default=False)
    role_similarity:Mapped[float]=mapped_column(Float,default=0);team_similarity:Mapped[float]=mapped_column(Float,default=0);domain_similarity:Mapped[float]=mapped_column(Float,default=0);company_match:Mapped[bool]=mapped_column(default=False);seniority_usefulness:Mapped[float]=mapped_column(Float,default=0);location_relevance:Mapped[float]=mapped_column(Float,default=0);relevance_score:Mapped[float]=mapped_column(Float,default=0);relevance_reason:Mapped[str]=mapped_column(Text)
    relationship_status:Mapped[str]=mapped_column(String(30),default="UNKNOWN");relationship_confidence:Mapped[float]=mapped_column(Float,default=0);evidence:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list);discovered_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);last_checked_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class ContactDiscoveryRunRecord(CandidateOwned, Base):
    __tablename__="contact_discovery_runs"
    id:Mapped[int]=mapped_column(primary_key=True);job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True);status:Mapped[str]=mapped_column(String(30),default="RUNNING",index=True)
    sources_checked:Mapped[int]=mapped_column(Integer,default=0);pages_checked:Mapped[int]=mapped_column(Integer,default=0);candidates_discovered:Mapped[int]=mapped_column(Integer,default=0);contacts_retained:Mapped[int]=mapped_column(Integer,default=0);errors_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)
    started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow);completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True));last_checked_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,index=True)

# Existing evaluation abstraction, extended rather than duplicated.
CandidateJobEvaluationRecord = JobScoreRecord

# Register guards for API, worker, CLI and test sessions alike.
from app.db import candidate_scope  # noqa: E402,F401
