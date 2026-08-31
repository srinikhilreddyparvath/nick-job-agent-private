import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.fit import FitAgent
from app.agents.scout import ScoutAgent
from app.connectors import CONNECTORS
from app.connectors.base import ConnectorError
from app.db.database import get_db
from app.models.application import ApplicationRead, ApplicationStatus
from app.models.job import Job, JobList, ScanRequest, ScanResult, ScoreResult
from app.models.profile import CandidateProfile, JobPreferences
from app.services.dedupe_service import DedupeService
from app.services.job_service import JobService
from app.services.filter_service import JobFilterService
from app.services.scoring_service import DeterministicScoringEngine
from app.models.ingestion import JobIngestResult,JobTextIngestRequest,JobUrlIngestRequest
from app.services.ingestion_service import JobIngestionService
from app.connectors.base import ConnectorError

router = APIRouter(prefix="/jobs", tags=["jobs"])
service = JobService(); dedupe = DedupeService()
data_dir = Path(__file__).resolve().parents[3] / "data"


def profile_and_preferences() -> tuple[CandidateProfile, JobPreferences]:
    profile_path = data_dir / "profile.example.json"; preferences_path = data_dir / "job_preferences.example.json"
    profile = CandidateProfile.model_validate_json(profile_path.read_text(encoding="utf-8")) if profile_path.exists() else CandidateProfile()
    preferences = JobPreferences.model_validate_json(preferences_path.read_text(encoding="utf-8")) if preferences_path.exists() else JobPreferences()
    return profile, preferences


@router.get("", response_model=JobList)
def list_jobs(recommendation: str | None = None,role_family:str|None=None,source:str|None=None,company:str|None=None,location:str|None=None,human_label:str|None=None, limit: int = Query(100, le=500), offset: int = 0, db: Session = Depends(get_db)):
    return service.list(db, recommendation, limit, offset,role_family,source,company,location,human_label)


@router.get("/{job_id}", response_model=Job)
def get_job(job_id: int, db: Session = Depends(get_db)):
    record = service.get(db, job_id)
    if not record: raise HTTPException(404, "Job not found")
    return service.to_schema(record)


@router.post("/scan", response_model=ScanResult)
def scan_jobs(request: ScanRequest, db: Session = Depends(get_db)):
    connector_type = CONNECTORS.get(request.connector.lower())
    if not connector_type: raise HTTPException(400, f"Unsupported connector. Choose: {', '.join(CONNECTORS)}")
    try: jobs = ScoutAgent().discover(connector_type(), request.identifier, request.company)
    except ConnectorError as exc: raise HTTPException(502, str(exc)) from exc
    created = []; duplicates = 0; filtered_out = 0
    _, preferences = profile_and_preferences()
    for job in jobs:
        if not JobFilterService().evaluate(job, preferences).passes: filtered_out += 1; continue
        if dedupe.find_duplicate(db, job): duplicates += 1; continue
        created.append(service.create(db, job).id)
    return ScanResult(connector=request.connector, discovered=len(jobs), created=len(created), duplicates=duplicates, filtered_out=filtered_out, job_ids=created)


@router.post("/{job_id}/score", response_model=ScoreResult)
def score_job(job_id: int, db: Session = Depends(get_db)):
    record = service.get(db, job_id)
    if not record: raise HTTPException(404, "Job not found")
    profile, preferences = profile_and_preferences(); result = FitAgent(DeterministicScoringEngine()).evaluate(service.to_schema(record), profile, preferences); service.save_score(db, job_id, result); return result


def change_status(job_id: int, status: ApplicationStatus, db: Session) -> ApplicationRead:
    application = service.set_status(db, job_id, status)
    if not application: raise HTTPException(404, "Job not found")
    return ApplicationRead.model_validate(application)


@router.post("/{job_id}/shortlist", response_model=ApplicationRead)
def shortlist_job(job_id: int, db: Session = Depends(get_db)): return change_status(job_id, ApplicationStatus.shortlisted, db)


@router.post("/{job_id}/skip", response_model=ApplicationRead)
def skip_job(job_id: int, db: Session = Depends(get_db)): return change_status(job_id, ApplicationStatus.skipped, db)


def ingestion_service():
    profile,preferences=profile_and_preferences();return JobIngestionService(profile,preferences)
@router.post("/ingest-url",response_model=JobIngestResult)
def ingest_url(data:JobUrlIngestRequest,db:Session=Depends(get_db)):
    try:return ingestion_service().ingest_url(db,str(data.url))
    except ConnectorError as exc:raise HTTPException(422,str(exc)) from exc
@router.post("/ingest-text",response_model=JobIngestResult)
def ingest_text(data:JobTextIngestRequest,db:Session=Depends(get_db)):
    try:return ingestion_service().ingest_text(db,data)
    except ConnectorError as exc:raise HTTPException(422,str(exc)) from exc
