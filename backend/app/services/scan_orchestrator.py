from datetime import datetime, timezone
from time import perf_counter
from typing import Callable

from sqlalchemy.orm import Session

from app.agents.fit import FitAgent
from app.connectors import CONNECTORS
from app.db.models import JobRecord, JobSourceRecord, ScanRunRecord
from app.services.dedupe_service import DedupeService
from app.services.family_scoring_service import FamilyScoringEngine
from app.services.filter_service import JobFilterService
from app.services.job_service import JobPersistenceError, JobService
from app.services.profile_service import load_preferences, load_profile
from app.services.role_family_service import DeterministicRoleFamilyClassifier
from app.services.scoring_service import DeterministicScoringEngine
from app.services.candidate_context_service import current_context, assert_current
from app.services.evidence_service import EvidenceService
from app.services.source_health_service import record_source_failure, record_source_success

ProgressCallback = Callable[[ScanRunRecord], None]


class ScanOrchestrator:
    def __init__(self, connectors: dict | None = None):
        self.connectors = connectors or CONNECTORS
        self.jobs = JobService()
        self.dedupe = DedupeService()
        self.filters = JobFilterService()
        self.scorer = FitAgent(DeterministicScoringEngine())
        self.profile = load_profile()
        self.preferences = load_preferences()
        self.classifier = DeterministicRoleFamilyClassifier()
        self.family_scorer = FamilyScoringEngine()

    @staticmethod
    def _notify(db: Session, run: ScanRunRecord, callback: ProgressCallback | None) -> None:
        db.add(run)
        db.commit()
        db.refresh(run)
        if callback:
            callback(run)

    def scan(self, db: Session, sources: list[JobSourceRecord], on_progress: ProgressCallback | None = None) -> ScanRunRecord:
        context = current_context()
        if context.pending: raise ValueError("Review and approve the uploaded resume before scanning")
        self.profile = context.profile
        self.preferences = context.preferences
        self.family_scorer = FamilyScoringEngine(EvidenceService(records=context.evidence))
        started = perf_counter()
        run = ScanRunRecord(status="running", source_count=len(sources))
        db.add(run)
        db.commit()
        db.refresh(run)
        run_id = run.id
        self._notify(db, run, on_progress)
        bands = {"exceptional": 0, "strong": 0, "possible": 0, "weak": 0, "skip": 0}
        errors: list[dict] = []
        by_source: dict[str, int] = {}
        by_family = {}

        try:
            for source_ref in sources:
                source_id = source_ref.id
                source = db.get(JobSourceRecord, source_id)
                if source.retry_after and source.retry_after > datetime.now(timezone.utc):
                    errors.append({"level": "source", "source_id": source.id, "company": source.company, "error": "Source is in bounded backoff", "failure_type": source.failure_type})
                    run.failed_source_count += 1
                    self._notify(db, run, on_progress)
                    continue
                source_started = perf_counter()
                source.last_scanned_at = datetime.now(timezone.utc)
                try:
                    connector_type = self.connectors.get(source.ats_type)
                    if connector_type is None:
                        raise ValueError(f"Connector {source.ats_type} is not active")
                    fetched = connector_type().fetch_jobs(source.board_identifier, source.company)
                    run.jobs_fetched += len(fetched)
                    by_source[source.ats_type] = by_source.get(source.ats_type, 0) + len(fetched)
                    self._notify(db, run, on_progress)

                    for index, job in enumerate(fetched, start=1):
                        try:
                            classification = self.classifier.classify(job)
                            job.role_family = classification.role_family
                            job.role_family_confidence = classification.confidence
                            job.role_family_reasons = classification.reasons
                            by_family[classification.role_family.value] = by_family.get(classification.role_family.value, 0) + 1
                            if not self.filters.evaluate(job, self.preferences).passes:
                                run.jobs_filtered += 1
                            else:
                                duplicate = self.dedupe.find_duplicate(db, job)
                                if duplicate:
                                    self.dedupe.record_alternate(db, duplicate, job)
                                    duplicate.last_seen_at = datetime.now(timezone.utc)
                                    duplicate.last_verified_at = datetime.now(timezone.utc)
                                    duplicate.posting_status = "LIKELY_LIVE"
                                    db.add(duplicate)
                                    run.jobs_deduplicated += 1
                                    run.duplicates_across_sources += int(duplicate.source != job.source)
                                    db.commit()
                                else:
                                    record = self.jobs.create(db, job)
                                    run = db.get(ScanRunRecord, run_id)
                                    run.jobs_added += 1
                                    self._notify(db, run, None)
                                    result = self.scorer.evaluate(job, self.profile, self.preferences)
                                    self.jobs.save_score(db, record.id, result, context)
                                    family = self.family_scorer.score(job, self.profile, self.preferences)
                                    self.jobs.save_family_fit(db, record.id, classification, family, context)
                                    run = db.get(ScanRunRecord, run_id)
                                    run.jobs_scored += 1
                                    bands[family.recommendation] += 1
                                    record = db.get(JobRecord, record.id)
                                    record.last_verified_at = datetime.now(timezone.utc)
                                    record.posting_status = "LIKELY_LIVE"
                                    db.add(record)
                                    db.commit()
                        except Exception as exc:
                            db.rollback()
                            run = db.get(ScanRunRecord, run_id)
                            error = {"level": "job", "source_id": source_id, "provider": getattr(job, "source", None), "external_id": str(getattr(job, "external_id", "unknown"))[:500], "error": type(exc).__name__}
                            if isinstance(exc, JobPersistenceError):
                                error["cause"] = exc.cause_type
                            errors.append(error)
                        if index % 25 == 0:
                            self._notify(db, run, on_progress)

                    source = db.get(JobSourceRecord, source_id)
                    record_source_success(source, len(fetched), (perf_counter() - source_started) * 1000)
                    source.jobs_discovered_total += len(fetched)
                    run = db.get(ScanRunRecord, run_id)
                    run.successful_source_count += 1
                except Exception as exc:
                    db.rollback()
                    source = db.get(JobSourceRecord, source_id)
                    run = db.get(ScanRunRecord, run_id)
                    record_source_failure(source, exc, (perf_counter() - source_started) * 1000)
                    run.failed_source_count += 1
                    errors.append({"level": "source", "source_id": source.id, "company": source.company, "error": type(exc).__name__, "failure_type": source.failure_type})
                db.add(source)
                self._notify(db, run, on_progress)

            assert_current(context)
            recomputed = self.jobs.evaluate_catalog(db, context)
            run = db.get(ScanRunRecord, run_id)
            run.jobs_scored += recomputed
            run.status = "completed_with_errors" if errors and run.successful_source_count else "failed" if errors else "completed"
            run.completed_at = datetime.now(timezone.utc)
            run.errors_json = errors
            run.duration_seconds = round(perf_counter() - started, 3)
            run.exceptional_count = bands["exceptional"]
            run.strong_count = bands["strong"]
            run.possible_count = bands["possible"]
            run.weak_count = bands["weak"]
            run.skip_count = bands["skip"]
            run.jobs_by_source_type = by_source
            run.jobs_by_role_family = by_family
            self._notify(db, run, on_progress)
            return run
        except Exception as exc:
            db.rollback()
            run = db.get(ScanRunRecord, run_id)
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.duration_seconds = round(perf_counter() - started, 3)
            run.errors_json = [*errors, {"level": "run", "error": type(exc).__name__}]
            self._notify(db, run, on_progress)
            return run
