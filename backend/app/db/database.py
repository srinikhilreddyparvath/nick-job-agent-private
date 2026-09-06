from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.db import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        additions={
          "jobs":{"role_family":"VARCHAR(40) DEFAULT 'UNKNOWN'","role_family_confidence":"FLOAT DEFAULT 0","role_family_reasons":"JSON DEFAULT '[]'","classification_method":"VARCHAR(40) DEFAULT 'deterministic_rules'","deterministic_family":"VARCHAR(40)","deterministic_confidence":"FLOAT","semantic_family":"VARCHAR(40)","semantic_confidence":"FLOAT","final_family":"VARCHAR(40)","classification_resolution_method":"VARCHAR(60)","family_fit_score":"FLOAT","family_component_scores":"JSON DEFAULT '{}'","family_recommendation":"VARCHAR(30)","family_strengths":"JSON DEFAULT '[]'","family_gaps":"JSON DEFAULT '[]'","matched_evidence_ids":"JSON DEFAULT '[]'","career_transition_flag":"BOOLEAN DEFAULT 0","career_transition_notes":"TEXT","raw_company":"VARCHAR(255)","canonical_company":"VARCHAR(255)","normalized_location":"VARCHAR(255)","description_fingerprint":"VARCHAR(64)","alternate_sources":"JSON DEFAULT '[]'","first_seen_at":"DATETIME","last_seen_at":"DATETIME","last_verified_at":"DATETIME","posting_status":"VARCHAR(30) DEFAULT 'UNKNOWN'"},
          "job_sources":{"company_id":"INTEGER","priority":"VARCHAR(20) DEFAULT 'NORMAL'","configuration":"JSON DEFAULT '{}'"},
          "scan_runs":{"jobs_by_source_type":"JSON DEFAULT '{}'","jobs_by_role_family":"JSON DEFAULT '{}'","duplicates_across_sources":"INTEGER DEFAULT 0","source_detection_failures":"INTEGER DEFAULT 0"},
          "job_feedback":{"human_role_family":"VARCHAR(40)"},
          "agent_runs":{"provider":"VARCHAR(40)","model":"VARCHAR(120)","prompt_version":"VARCHAR(80)","temperature":"FLOAT","evidence_ids_used":"JSON DEFAULT '[]'","sources_used":"JSON DEFAULT '[]'","input_tokens":"INTEGER DEFAULT 0","output_tokens":"INTEGER DEFAULT 0","cached_tokens":"INTEGER DEFAULT 0","estimated_cost":"FLOAT DEFAULT 0","latency_ms":"INTEGER DEFAULT 0"},
          "semantic_analyses":{"cached_tokens":"INTEGER DEFAULT 0"},
          "company_research":{"cached_tokens":"INTEGER DEFAULT 0"},
          "application_packages":{"job_requirements_json":"JSON DEFAULT '[]'","cover_letter_evidence_ids":"JSON DEFAULT '[]'"}}
        additions["application_queue_items"]={"lease_owner":"VARCHAR(120)","lease_expires_at":"DATETIME","heartbeat_at":"DATETIME","submit_started_at":"DATETIME"}
        with engine.begin() as connection:
            inspector=inspect(connection)
            for table,columns in additions.items():
                existing={column["name"] for column in inspector.get_columns(table)}
                for name,ddl in columns.items():
                    if name not in existing: connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{name}" {ddl}'))
