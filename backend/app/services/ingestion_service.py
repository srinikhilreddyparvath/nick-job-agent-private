import hashlib,re
from sqlalchemy.orm import Session
from app.connectors.generic_site import extract_jsonld_jobs
from app.connectors.base import ConnectorError
from app.models.ingestion import JobIngestResult,JobTextIngestRequest
from app.models.job import Job
from app.models.profile import CandidateProfile,JobPreferences
from app.services.dedupe_service import DedupeService
from app.services.family_scoring_service import FamilyScoringEngine
from app.services.job_service import JobService
from app.services.role_family_service import DeterministicRoleFamilyClassifier
from app.services.scoring_service import DeterministicScoringEngine
from app.services.candidate_context_service import current_context, assert_current
from app.services.evidence_service import EvidenceService
from app.agents.fit import FitAgent
import httpx

class JobIngestionService:
 def __init__(self,profile:CandidateProfile,preferences:JobPreferences):self.profile=profile;self.preferences=preferences;self.jobs=JobService();self.dedupe=DedupeService();self.classifier=DeterministicRoleFamilyClassifier();self.family=FamilyScoringEngine();self.baseline=FitAgent(DeterministicScoringEngine())
 def _persist(self,db:Session,job:Job)->JobIngestResult:
    context = current_context()
    if context.pending: raise ValueError("Approve the replacement resume before scoring jobs")
    family_scorer = FamilyScoringEngine(EvidenceService(records=context.evidence))
    classification=self.classifier.classify(job);job.role_family=classification.role_family;job.role_family_confidence=classification.confidence;job.role_family_reasons=classification.reasons
    duplicate=self.dedupe.find_duplicate(db,job)
    if duplicate:self.dedupe.record_alternate(db,duplicate,job);self.jobs.evaluate_catalog(db,context);return JobIngestResult(status="duplicate",job=self.jobs.to_schema(self.jobs.get(db,duplicate.id)),duplicate=True,message="Matched existing opening; alternate source recorded")
    record=self.jobs.create(db,job);baseline=self.baseline.evaluate(job,context.profile,context.preferences);self.jobs.save_score(db,record.id,baseline,context);family=family_scorer.score(job,context.profile,context.preferences);self.jobs.save_family_fit(db,record.id,classification,family,context);assert_current(context);return JobIngestResult(status="saved",job=self.jobs.to_schema(self.jobs.get(db,record.id)),message="Job normalized, classified, saved, and scored")
 def ingest_url(self,db:Session,url:str)->JobIngestResult:
    try:r=httpx.get(url,timeout=20,follow_redirects=True,headers={"User-Agent":"CareerIntelligenceAgent/0.1"});r.raise_for_status()
    except Exception as exc:raise ConnectorError(f"job_url_fetch_failed: {exc}; use /jobs/ingest-text as fallback") from exc
    source="linkedin_reference" if "linkedin.com" in str(r.url).lower() else "manual_url";jobs=extract_jsonld_jobs(r.text,str(r.url),source=source)
    if not jobs:raise ConnectorError("no_public_structured_job_found; paste the job description via /jobs/ingest-text")
    job=jobs[0];job.source=source;return self._persist(db,job)
 def ingest_text(self,db:Session,data:JobTextIngestRequest)->JobIngestResult:
    source="linkedin_reference" if "linkedin.com" in str(data.source_url).lower() else "manual_url";title=data.title or data.job_description_text.splitlines()[0].strip()[:255];company=data.company or "Unknown company"
    if not title:raise ConnectorError("title_required_when_text_has_no_heading")
    external=hashlib.sha256((str(data.source_url)+title+company).encode()).hexdigest()[:24];job=Job(external_id=external,source=source,company=company,title=title,location=data.location,description=data.job_description_text,requirements=[],preferred_qualifications=[],apply_url=data.source_url,source_url=data.source_url);return self._persist(db,job)

class JobAlertIngestionService:
 def ingest(self,*_args,**_kwargs):raise NotImplementedError("Email/job-alert ingestion is modeled only; no OAuth is configured")
class JobDiscoverySearchProvider:
 def discover(self,*_args,**_kwargs):raise NotImplementedError("Authorized search-provider integration is not configured; search result pages are never scraped")
