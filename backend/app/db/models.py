from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_job_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    source: Mapped[str] = mapped_column(String(50), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    normalized_title: Mapped[str] = mapped_column(String(255), index=True)
    location: Mapped[str | None] = mapped_column(String(255))
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
    family_fit_score:Mapped[float|None]=mapped_column(Float)
    family_component_scores:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict)
    family_recommendation:Mapped[str|None]=mapped_column(String(30))
    family_strengths:Mapped[list[str]]=mapped_column(JSON,default=list)
    family_gaps:Mapped[list[str]]=mapped_column(JSON,default=list)
    matched_evidence_ids:Mapped[list[str]]=mapped_column(JSON,default=list)
    career_transition_flag:Mapped[bool]=mapped_column(default=False)
    career_transition_notes:Mapped[str|None]=mapped_column(Text)
    raw_company:Mapped[str|None]=mapped_column(String(255))
    canonical_company:Mapped[str|None]=mapped_column(String(255),index=True)
    normalized_location:Mapped[str|None]=mapped_column(String(255),index=True)
    description_fingerprint:Mapped[str|None]=mapped_column(String(64),index=True)
    alternate_sources:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list)

    scores: Mapped[list["JobScoreRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    application: Mapped["ApplicationRecord | None"] = relationship(back_populates="job", uselist=False)
    feedback: Mapped["JobFeedbackRecord | None"] = relationship(back_populates="job", uselist=False)


class JobScoreRecord(Base):
    __tablename__ = "job_scores"

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


class ApplicationRecord(Base):
    __tablename__ = "applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="discovered", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[JobRecord] = relationship(back_populates="application")
    events: Mapped[list["ApplicationEventRecord"]] = relationship(back_populates="application", cascade="all, delete-orphan")


class ApplicationEventRecord(Base):
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


class JobFeedbackRecord(Base):
    __tablename__="job_feedback"
    id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),unique=True,index=True)
    human_label:Mapped[str]=mapped_column(String(20)); human_notes:Mapped[str|None]=mapped_column(Text)
    labeled_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    job:Mapped[JobRecord]=relationship(back_populates="feedback")
    human_role_family:Mapped[str|None]=mapped_column(String(40))


class CompanyRecord(Base):
    __tablename__="companies"
    id:Mapped[int]=mapped_column(primary_key=True); name:Mapped[str]=mapped_column(String(255)); canonical_name:Mapped[str]=mapped_column(String(255),unique=True,index=True)
    website_url:Mapped[str|None]=mapped_column(Text); careers_url:Mapped[str|None]=mapped_column(Text); company_type:Mapped[str]=mapped_column(String(40),default="OTHER"); priority:Mapped[str]=mapped_column(String(20),default="NORMAL"); enabled:Mapped[bool]=mapped_column(default=True); notes:Mapped[str|None]=mapped_column(Text); detected_ats:Mapped[str|None]=mapped_column(String(50)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)


class AgentRunRecord(Base):
    __tablename__="agent_runs"
    id:Mapped[int]=mapped_column(primary_key=True); agent_type:Mapped[str]=mapped_column(String(40),index=True); objective:Mapped[str]=mapped_column(Text); job_id:Mapped[int|None]=mapped_column(ForeignKey("jobs.id")); status:Mapped[str]=mapped_column(String(40),default="queued",index=True)
    started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True)); completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    input_state_json:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict); output_state_json:Mapped[dict[str,Any]]=mapped_column(JSON,default=dict); actions_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); errors_json:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); requires_human_review:Mapped[bool]=mapped_column(default=False)
    provider:Mapped[str|None]=mapped_column(String(40)); model:Mapped[str|None]=mapped_column(String(120)); prompt_version:Mapped[str|None]=mapped_column(String(80)); temperature:Mapped[float|None]=mapped_column(Float)
    evidence_ids_used:Mapped[list[str]]=mapped_column(JSON,default=list); sources_used:Mapped[list[str]]=mapped_column(JSON,default=list); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0)


class EvidenceEmbeddingRecord(Base):
    __tablename__="evidence_embeddings"
    id:Mapped[int]=mapped_column(primary_key=True); evidence_id:Mapped[str]=mapped_column(String(80),index=True); evidence_version:Mapped[str]=mapped_column(String(64),index=True); provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); embedding_version:Mapped[str]=mapped_column(String(80)); vector:Mapped[list[float]]=mapped_column(JSON); generated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint("evidence_id","evidence_version","provider","model",name="uq_evidence_embedding_version"),)


class SemanticAnalysisRecord(Base):
    __tablename__="semantic_analyses"
    id:Mapped[int]=mapped_column(primary_key=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True); fingerprint:Mapped[str]=mapped_column(String(64),unique=True,index=True); deterministic_score:Mapped[float|None]=mapped_column(Float); semantic_score:Mapped[float]=mapped_column(Float); blended_score:Mapped[float|None]=mapped_column(Float); report_json:Mapped[dict[str,Any]]=mapped_column(JSON); provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); prompt_version:Mapped[str]=mapped_column(String(80)); evidence_version:Mapped[str]=mapped_column(String(64)); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)


class CompanyResearchRecord(Base):
    __tablename__="company_research"
    id:Mapped[int]=mapped_column(primary_key=True); company_id:Mapped[int|None]=mapped_column(ForeignKey("companies.id"),index=True); job_id:Mapped[int]=mapped_column(ForeignKey("jobs.id"),index=True); fingerprint:Mapped[str]=mapped_column(String(64),unique=True,index=True); summary:Mapped[str]=mapped_column(Text); technical_focus:Mapped[list[str]]=mapped_column(JSON,default=list); research_areas:Mapped[list[str]]=mapped_column(JSON,default=list); products:Mapped[list[str]]=mapped_column(JSON,default=list); role_context:Mapped[str]=mapped_column(Text,default=""); relevant_teams:Mapped[list[str]]=mapped_column(JSON,default=list); culture_signals:Mapped[list[str]]=mapped_column(JSON,default=list); hiring_signals:Mapped[list[str]]=mapped_column(JSON,default=list); sources:Mapped[list[dict[str,Any]]]=mapped_column(JSON,default=list); report_json:Mapped[dict[str,Any]]=mapped_column(JSON); generated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow); provider:Mapped[str]=mapped_column(String(40)); model:Mapped[str]=mapped_column(String(120)); prompt_version:Mapped[str]=mapped_column(String(80)); input_tokens:Mapped[int]=mapped_column(Integer,default=0); output_tokens:Mapped[int]=mapped_column(Integer,default=0); estimated_cost:Mapped[float]=mapped_column(Float,default=0); latency_ms:Mapped[int]=mapped_column(Integer,default=0)
