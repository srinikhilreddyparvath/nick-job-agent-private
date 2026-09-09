from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import Text, select

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import AgentRunRecord, JobRecord, JobSourceRecord, ScanRunRecord
from app.models.job import Job
from app.services.career_intelligence_service import CareerIntelligenceService
from app.services.job_service import JobPersistenceError, JobService
from app.services.scan_orchestrator import ScanOrchestrator
from app.worker import ApplicationWorker


LONG_LOCATION = (
    "Charlotte, NC; Raleigh, NC; Tampa, FL; Orlando, FL; Pittsburgh, PA; Richmond, VA; "
    "Jacksonville, FL; Columbus, OH; Dallas, TX; Houston, TX; Minneapolis, MN; Nashville, TN; "
    "Kansas City, MO; St. Louis, MO; Tempe, AZ; Indianapolis, IN; Oklahoma City, OK; "
    "New Orleans, LA; Charleston, SC; Atlanta, GA"
)


def make_job(external_id: str, **changes) -> Job:
    values = {
        "external_id": external_id,
        "source": "greenhouse",
        "company": "Fixture Health Systems",
        "title": "Machine Learning Research Engineer",
        "location": "Remote",
        "description": "Build Python machine-learning evaluation and ranking systems with cross-functional partners.",
        "apply_url": f"https://jobs.example.test/roles/{external_id}",
        "source_url": f"https://jobs.example.test/roles/{external_id}",
    }
    values.update(changes)
    return Job(**values)


def test_provider_controlled_job_fields_use_durable_text_columns():
    columns = {column.name: column.type for column in JobRecord.__table__.columns}
    for name in ("external_id", "company", "title", "normalized_title", "location", "raw_company", "canonical_company", "normalized_location", "apply_url", "canonical_apply_url", "source_url"):
        assert isinstance(columns[name], Text), name


def test_exact_long_multilocation_and_long_provider_values_persist():
    db = SessionLocal()
    try:
        long_url = "https://jobs.example.test/apply?" + "&".join(f"parameter{index}={'x' * 30}" for index in range(30))
        job = make_job(
            "provider-id-" + "x" * 400,
            company="Provider " + "C" * 320,
            title="Principal " + "Research Operations " * 25,
            location=LONG_LOCATION,
            apply_url=long_url,
            source_url=long_url,
        )
        record = JobService().create(db, job)
        persisted = db.get(JobRecord, record.id)
        assert len(LONG_LOCATION) == 295
        assert persisted.location == LONG_LOCATION
        assert persisted.normalized_location == LONG_LOCATION
        assert persisted.title == job.title
        assert persisted.company == job.company
        assert persisted.apply_url == long_url
        assert persisted.canonical_apply_url.startswith("https://jobs.example.test/apply?")
    finally:
        db.close()


def test_job_service_rolls_back_failed_flush_and_session_remains_usable():
    db = SessionLocal()
    try:
        JobService().create(db, make_job("duplicate"))
        with pytest.raises(JobPersistenceError) as error:
            JobService().create(db, make_job("duplicate", apply_url="https://jobs.example.test/duplicate-2"))
        assert error.value.cause_type == "IntegrityError"
        recovered = JobService().create(db, make_job("after-failure"))
        assert recovered.id is not None
    finally:
        db.close()


class ThreeJobConnector:
    def fetch_jobs(self, _identifier, _company):
        return [
            make_job("long-location", title="Machine Learning Research Engineer", location=LONG_LOCATION, description="Build Python retrieval evaluation systems."),
            make_job("deliberately-invalid", title="Senior Data Scientist, Experimentation", description="Design causal inference experiments and metrics."),
            make_job("valid-after-invalid", title="AI Product Manager, Platform", description="Lead platform roadmaps, analytics, and launches."),
        ]


class FailingConnector:
    def fetch_jobs(self, _identifier, _company):
        raise TimeoutError("fixture source timeout")


class FailOneCreate(JobService):
    def create(self, db, job):
        if job.external_id == "deliberately-invalid":
            duplicate = JobRecord(
                external_id="long-location", source="greenhouse", company="Collision", title="Collision",
                normalized_title="collision", location="Remote", remote_type="unspecified", description="",
                requirements=[], preferred_qualifications=[], apply_url="https://invalid.example/a",
                canonical_apply_url="https://invalid.example/a", source_url="https://invalid.example/a",
            )
            db.add(duplicate)
            db.flush()
        return super().create(db, job)


def test_scan_records_one_bad_job_continues_and_reports_progress():
    db = SessionLocal()
    try:
        source = JobSourceRecord(company="Fixture", ats_type="greenhouse", board_identifier="fixture")
        db.add(source)
        db.commit()
        scanner = ScanOrchestrator(connectors={"greenhouse": ThreeJobConnector})
        scanner.jobs = FailOneCreate()
        scanner.filters.evaluate = lambda *_args: SimpleNamespace(passes=True)
        snapshots = []
        run = scanner.scan(db, [source], on_progress=lambda current: snapshots.append((current.jobs_fetched, current.jobs_added, current.jobs_scored)))
        assert run.status == "completed_with_errors"
        assert run.jobs_fetched == 3
        assert run.jobs_added == 2
        assert run.jobs_scored == 2
        assert db.scalar(select(JobRecord).where(JobRecord.external_id == "valid-after-invalid"))
        assert any(error["level"] == "job" and error["external_id"] == "deliberately-invalid" for error in run.errors_json)
        assert snapshots[-1] == (3, 2, 2)
    finally:
        db.close()


def test_single_source_failure_does_not_stop_healthy_source():
    db = SessionLocal()
    try:
        failed = JobSourceRecord(company="Unavailable", ats_type="failing", board_identifier="failed")
        healthy = JobSourceRecord(company="Healthy", ats_type="greenhouse", board_identifier="healthy")
        db.add_all([failed, healthy])
        db.commit()
        scanner = ScanOrchestrator(connectors={"failing": FailingConnector, "greenhouse": ThreeJobConnector})
        scanner.filters.evaluate = lambda *_args: SimpleNamespace(passes=False)
        run = scanner.scan(db, [failed, healthy])
        assert run.status == "completed_with_errors"
        assert run.failed_source_count == 1
        assert run.successful_source_count == 1
        assert run.jobs_fetched == 3
    finally:
        db.close()


class FatalScanner:
    def scan(self, db, _sources, on_progress=None):
        broken = JobRecord(external_id="broken")
        db.add(broken)
        db.flush()


def test_run_failure_rolls_back_becomes_terminal_and_next_run_can_process(monkeypatch):
    db = SessionLocal()
    try:
        source = JobSourceRecord(company="Fixture", ats_type="greenhouse", board_identifier="fixture")
        db.add(source)
        first = AgentRunRecord(agent_type="career_intelligence", objective="test", status="queued", input_state_json={"scan_required": True}, actions_json=[])
        db.add(first)
        db.commit()
        service = CareerIntelligenceService(get_settings(), scanner=FatalScanner())
        completed = service.process_next(db, worker_id="worker-one")
        assert completed.status == "failed"
        assert completed.completed_at is not None
        assert completed.errors_json[0]["error"] == "IntegrityError"
        second = AgentRunRecord(agent_type="career_intelligence", objective="next", status="queued", input_state_json={"scan_required": False}, actions_json=[])
        db.add(second)
        db.commit()
        processed = CareerIntelligenceService(get_settings()).process_next(db, worker_id="worker-one")
        assert processed.id == second.id
        assert processed.status == "completed"
    finally:
        db.close()


def test_worker_restart_recovers_abandoned_running_run():
    db = SessionLocal()
    try:
        run = AgentRunRecord(
            agent_type="career_intelligence", objective="interrupted", status="running",
            started_at=datetime.now(timezone.utc), input_state_json={"worker_id": "old-process"}, actions_json=[],
        )
        db.add(run)
        scan = ScanRunRecord(status="running", source_count=20)
        db.add(scan)
        db.commit()
        assert CareerIntelligenceService.recover_abandoned(db, "new-process") == 1
        db.refresh(run)
        assert run.status == "failed"
        assert run.completed_at is not None
        assert run.errors_json == [{"error": "WORKER_INTERRUPTED", "recoverable": True}]
        db.refresh(scan)
        assert scan.status == "failed"
        assert scan.completed_at is not None
    finally:
        db.close()


def test_worker_boundary_contains_unexpected_career_run_failure(monkeypatch):
    db = SessionLocal()
    try:
        monkeypatch.setattr("app.worker.CareerIntelligenceService.process_next", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("fixture")))
        result = ApplicationWorker(worker_id="survivor").run_once(db)
        assert result == {"status": "CAREER_INTELLIGENCE_FAILED", "error": "RuntimeError"}
        assert db.is_active
    finally:
        db.close()
