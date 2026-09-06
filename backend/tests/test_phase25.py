import json
from app.connectors.generic_site import extract_jsonld_jobs
from app.connectors.smartrecruiters import SmartRecruitersConnector
from app.connectors.workday import WorkdayConnector
from app.models.job import Job
from app.models.profile import CandidateProfile,JobPreferences
from app.models.role_family import RoleFamily
from app.services.ats_detector import AtsDetector
from app.services.dedupe_service import DedupeService
from app.services.family_scoring_service import FamilyScoringEngine
from app.services.filter_service import JobFilterService
from app.services.job_service import JobService
from app.services.normalization_service import normalize_company,normalize_location
from app.services.role_family_service import DeterministicRoleFamilyClassifier
from app.services.scan_orchestrator import ScanOrchestrator
from app.services.company_service import CompanyService
from app.services.source_service import SourceService
from app.db.database import SessionLocal
from app.models.company import CompanyCreate
from app.models.source import JobSourceCreate

def job(title,description="",company="Example AI",source="test",external_id="1",url="https://example.com/jobs/1"):
 return Job(external_id=external_id,source=source,company=company,title=title,location="San Francisco, CA",description=description,requirements=[],preferred_qualifications=[],apply_url=url,source_url=url)

def test_role_family_classifications():
 classifier=DeterministicRoleFamilyClassifier()
 assert classifier.classify(job("Research Engineer, Agents","Build applied AI agent evaluation systems")).role_family==RoleFamily.research_ai
 assert classifier.classify(job("Senior Data Scientist, Experimentation","Statistical measurement and causal experimentation")).role_family==RoleFamily.data_science
 assert classifier.classify(job("Senior Product Manager, AI Platform","Lead product strategy with ML engineering stakeholders")).role_family==RoleFamily.product_management
 assert classifier.classify(job("Software Engineer, Backend","Build Go APIs and databases")).role_family==RoleFamily.unknown

def test_family_scoring_and_pm_transition():
 profile=CandidateProfile();prefs=JobPreferences();engine=FamilyScoringEngine();classifier=DeterministicRoleFamilyClassifier()
 research=job("Applied Scientist","Applied research, machine learning evaluation, Python and production experiments");research.role_family=classifier.classify(research).role_family
 assert set(engine.score(research,profile,prefs).family_component_scores)=={"research_alignment","technical_alignment","ml_ai_depth","experience_alignment","skills_alignment","production_research_fit","location_compensation"}
 pm=job("AI Product Manager","Lead AI platform product strategy, stakeholder alignment, launch planning and engineering collaboration");pm.role_family=classifier.classify(pm).role_family;result=engine.score(pm,profile,prefs)
 assert result.career_transition_flag and "not prior Product Manager employment" in result.career_transition_notes

def test_hard_filter_does_not_require_search_keywords():
 role=job("Senior Data Scientist, Experimentation","Build statistical causal models and product experiments");result=JobFilterService().evaluate(role,JobPreferences(preferred_domains=["Search","Ranking","Personalization"]));assert result.passes

def test_hard_filter_keeps_unknown_employment_type_neutral():
 role=job("Research Engineer","Build retrieval and ranking systems");role.employment_type=None
 result=JobFilterService().evaluate(role,JobPreferences(employment_types=["full-time"]));assert result.passes

def test_generic_jsonld_parsing():
 payload={"@context":"https://schema.org","@type":"JobPosting","identifier":{"value":"jp-1"},"title":"AI Product Manager","description":"Lead AI platform strategy","datePosted":"2026-08-01","employmentType":"FULL_TIME","hiringOrganization":{"name":"OpenAI, Inc."},"jobLocation":{"address":{"addressLocality":"San Francisco","addressRegion":"CA"}},"baseSalary":{"currency":"USD","value":{"minValue":180000,"maxValue":220000}},"url":"/jobs/jp-1"}
 jobs=extract_jsonld_jobs(f'<script type="application/ld+json">{json.dumps(payload)}</script>',"https://example.com/careers")
 assert jobs[0].title=="AI Product Manager" and jobs[0].salary_min==180000 and jobs[0].location=="San Francisco, CA"

def test_smartrecruiters_pagination_and_normalization(monkeypatch):
 connector=SmartRecruitersConnector();calls=[]
 def fake(method,url,**kwargs):
  calls.append(url)
  if url.endswith("/postings"):return {"content":[{"id":"sr-1"}],"totalFound":1}
  return {"id":"sr-1","name":"Data Scientist, Measurement","company":{"name":"Acme"},"location":{"city":"San Francisco","region":"CA","country":"US"},"remote":False,"typeOfEmployment":{"label":"Full-time"},"jobAd":{"sections":{"jobDescription":{"text":"<p>Statistical experimentation</p>"},"qualifications":{"text":"Python"}}},"postingUrl":"https://jobs.smartrecruiters.com/acme/sr-1","releasedDate":"2026-08-01"}
 monkeypatch.setattr(connector,"request_json",fake);jobs=connector.fetch_jobs("acme","Acme");assert len(jobs)==1 and jobs[0].external_id=="sr-1" and len(calls)==2

def test_ats_detection_all_supported_patterns():
 detector=AtsDetector();cases={"greenhouse":"https://boards.greenhouse.io/acme","lever":"https://jobs.lever.co/acme","ashby":"https://jobs.ashbyhq.com/acme","smartrecruiters":"https://jobs.smartrecruiters.com/acme","workday":"https://acme.wd5.myworkdayjobs.com/External"}
 for expected,url in cases.items():assert detector.detect("Acme",url,html=f'<a href="{url}">Jobs</a>').detected_ats==expected
 generic=detector.detect("Acme","https://acme.com/careers",html='<script type="application/ld+json">{"@type":"JobPosting"}</script>');assert generic.detected_ats=="generic_company_site"

def test_company_registry_and_company_source_relationship(client):
 company=client.post("/companies",json={"name":"OpenAI, Inc.","website_url":"https://openai.com","careers_url":"https://openai.com/careers","company_type":"AI_STARTUP","priority":"HIGH","enabled":True}).json();assert company["canonical_name"]=="openai"
 source=client.post("/sources",json={"company":"OpenAI","company_id":company["id"],"ats_type":"generic_company_site","board_identifier":"https://openai.com/careers","enabled":False,"priority":"HIGH"});assert source.status_code==201
 assert client.get("/companies").json()[0]["source_count"]==1

def test_manual_text_ingestion_linkedin_and_role_filter(client):
 data={"source_url":"https://www.linkedin.com/jobs/view/123","company":"Acme AI","title":"Senior Product Manager, AI Platform","job_description_text":"Lead AI product strategy with machine learning engineering, stakeholder alignment, experimentation, and launch planning."}
 response=client.post("/jobs/ingest-text",json=data);assert response.status_code==200;result=response.json();assert result["job"]["source"]=="linkedin_reference" and result["job"]["role_family"]=="PRODUCT_MANAGEMENT" and result["job"]["career_transition_flag"]
 assert client.get("/jobs?role_family=PRODUCT_MANAGEMENT").json()["total"]==1

def test_manual_url_ingestion_from_public_jsonld(client,monkeypatch):
 import app.services.ingestion_service as module
 payload={"@context":"https://schema.org","@type":"JobPosting","identifier":"url-1","title":"Research Scientist","description":"Applied AI research and model evaluation","hiringOrganization":{"name":"Public AI"},"url":"https://public.example/jobs/1"}
 class Response:
  text=f'<script type="application/ld+json">{json.dumps(payload)}</script>';url="https://public.example/jobs/1"
  def raise_for_status(self):pass
 monkeypatch.setattr(module.httpx,"get",lambda *args,**kwargs:Response())
 result=client.post("/jobs/ingest-url",json={"url":"https://public.example/jobs/1"});assert result.status_code==200 and result.json()["job"]["role_family"]=="RESEARCH_AI"

def test_workday_supported_public_cxs_format(monkeypatch):
 connector=WorkdayConnector()
 monkeypatch.setattr(connector,"request_json",lambda *args,**kwargs:{"jobPostings":[{"title":"Senior Data Scientist","externalPath":"/job/1","locationsText":"Remote US","bulletFields":["wd-1"],"postedOn":"Posted Today"}],"total":1})
 jobs=connector.fetch_jobs("acme|External|https://acme.wd5.myworkdayjobs.com","Acme");assert jobs[0].external_id=="wd-1" and jobs[0].title=="Senior Data Scientist"

def test_cross_source_dedupe_alternate_and_normalization():
 first=job("Senior Data Scientist","Statistical experimentation and causal measurement",company="OpenAI, Inc.",source="generic_company_site",url="https://openai.com/jobs/1")
 second=job("Senior Data Scientist","Statistical experimentation and causal measurement",company="OPENAI",source="linkedin_reference",external_id="li-1",url="https://linkedin.com/jobs/1")
 with SessionLocal() as db:
  service=JobService();record=service.create(db,first);duplicate=DedupeService().find_duplicate(db,second);assert duplicate.id==record.id;DedupeService().record_alternate(db,duplicate,second);assert len(db.get(type(record),record.id).alternate_sources)==1
 assert normalize_company("OpenAI, Inc.")==normalize_company("OPENAI") and normalize_location("Mountain View, CA")=="South Bay"

def test_human_role_family_correction(client):
 saved=client.post("/jobs/ingest-text",json={"source_url":"https://example.com/manual/1","company":"Acme","title":"Technical Lead","job_description_text":"Lead product requirements for an AI data platform with stakeholders and launch planning."}).json();job_id=saved["job"]["id"]
 feedback=client.post(f"/jobs/{job_id}/feedback",json={"human_label":"good","human_notes":"PM transition","human_role_family":"PRODUCT_MANAGEMENT"});assert feedback.status_code==201
 result=client.get(f"/jobs/{job_id}").json();assert result["role_family"]=="PRODUCT_MANAGEMENT" and result["classification_method"]=="human_override"

def test_realistic_company_to_scored_job_discovery_smoke():
 class PublicBoardFixtureConnector:
  def fetch_jobs(self,identifier,company):
   assert identifier=="example-ai"
   posting=job("Applied Scientist, AI Evaluation","Applied machine learning research, model evaluation, Python, experimentation, and production ML systems",company=company,source="greenhouse",external_id="live-ready-1",url="https://boards.greenhouse.io/example-ai/jobs/live-ready-1");posting.location="Metro City";posting.employment_type="full-time";return [posting]
 detection=AtsDetector().detect("Example AI", "https://example.ai/careers", html='<a href="https://boards.greenhouse.io/example-ai">Open roles</a>')
 assert detection.detected_ats=="greenhouse" and detection.board_identifier=="example-ai"
 with SessionLocal() as db:
  company=CompanyService().create(db,CompanyCreate(name="Example AI",website_url="https://example.ai",careers_url="https://example.ai/careers",company_type="AI_STARTUP",priority="HIGH"))
  source=SourceService().create(db,JobSourceCreate(company=company.name,company_id=company.id,ats_type=detection.detected_ats,board_identifier=detection.board_identifier,careers_url=company.careers_url,priority="HIGH"))
  run=ScanOrchestrator(connectors={"greenhouse":PublicBoardFixtureConnector}).scan(db,[source])
  discovered=JobService().list(db,role_family="RESEARCH_AI")
  assert run.status=="completed" and run.jobs_fetched==1 and run.jobs_added==1 and run.jobs_scored==1
  assert run.jobs_by_role_family["RESEARCH_AI"]==1 and len(discovered.items)==1
  assert discovered.items[0].family_fit_score is not None and discovered.items[0].recommendation is not None
