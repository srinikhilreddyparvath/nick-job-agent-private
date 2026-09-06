from pathlib import Path

from app.agents.fit import FitAgent
from app.agents.orchestrator import AgentOrchestrator
from app.agents.scout import ScoutAgent
from app.db.database import SessionLocal
from app.models.job import Job
from app.models.profile import CandidateProfile,JobPreferences
from app.services.agent_service import AgentRunService
from app.services.evaluation_service import RankingEvaluationService
from app.services.evidence_service import EvidenceService
from app.services.job_service import JobService
from app.services.policy_service import AnswerBankService,WorkAuthorizationService
from app.services.scoring_service import DeterministicScoringEngine


class MockConnector:
    def fetch_jobs(self,identifier,company):
        return [Job(external_id="mock-1",source="greenhouse",company=company,title="Applied Scientist - Search",location="Metro City, USA",remote_type="hybrid",employment_type="full-time",description="Machine learning research for information retrieval, ranking, Python, experimentation, and semantic search",requirements=["Python","Information Retrieval"],preferred_qualifications=["Applied research"],apply_url=f"https://example.com/{identifier}/apply",source_url=f"https://example.com/{identifier}")]


def test_resume_and_canonical_profile(client):
    profile=client.get("/profile")
    assert profile.status_code==200
    assert profile.json()["identity"]["legal_name"]=="Alex Morgan"
    assert len(profile.json()["experience"])==1


def test_evidence_creation_and_retrieval(client):
    service=EvidenceService()
    assert service.get_by_id("EXPERIENCE_002").verified
    assert service.search(company="Northstar",domains=["ranking"])
    assert service.search(skills=["Python"])
    assert service.search(category="experience")
    assert service.search(text_query="ranking variants")
    assert client.get("/profile/evidence?company=Northstar").status_code==200
    assert client.get("/profile/evidence/EXPERIENCE_002").json()["category"]=="experience"


def test_preferences_answers_and_work_authorization():
    data=Path(__file__).resolve().parents[2]/"data"/"preferences.example.json"
    prefs=JobPreferences.model_validate_json(data.read_text(encoding="utf-8"))
    assert "Research Engineer" in prefs.preferred_titles
    assert prefs.compensation.salary_is_hard_filter is False
    bank=AnswerBankService().all(); assert bank["approved_structured"][0].answer_type=="APPROVED_STRUCTURED"
    service=WorkAuthorizationService()
    assert service.assess("Are you legally authorized to work in the United States?").answer=="YES"
    assert service.assess("Do you have unrestricted permanent authorization without sponsorship?").requires_human_review


def test_source_crud_enable_disable(client):
    created=client.post("/sources",json={"company":"Mock AI","ats_type":"greenhouse","board_identifier":"mock","careers_url":"https://example.com/careers","enabled":True,"scan_frequency":"manual"})
    assert created.status_code==201; source_id=created.json()["id"]
    assert client.put(f"/sources/{source_id}",json={"company":"Mock Research AI"}).json()["company"]=="Mock Research AI"
    assert client.patch(f"/sources/{source_id}/enabled",json={"enabled":False}).json()["enabled"] is False
    assert client.patch(f"/sources/{source_id}/enabled",json={"enabled":True}).json()["enabled"] is True
    assert client.delete(f"/sources/{source_id}").status_code==204


def test_scan_orchestration_auto_score_dedupe_and_history(client,monkeypatch):
    import app.services.scan_orchestrator as module
    monkeypatch.setitem(module.CONNECTORS,"greenhouse",MockConnector)
    source=client.post("/sources",json={"company":"Mock AI","ats_type":"greenhouse","board_identifier":"mock","enabled":True}).json()
    first=client.post(f"/sources/{source['id']}/scan")
    assert first.status_code==200; result=first.json(); assert result["jobs_added"]==1 and result["jobs_scored"]==1
    jobs=client.get("/jobs").json()["items"]; assert jobs[0]["fit_score"] is not None and jobs[0]["component_scores"]
    second=client.post("/sources/scan-all").json(); assert second["jobs_deduplicated"]==1 and second["jobs_added"]==0
    scans=client.get("/scans"); assert scans.status_code==200 and len(scans.json())==2
    assert client.get(f"/scans/{result['id']}").status_code==200


def test_human_feedback_and_evaluation_state(client):
    with SessionLocal() as db:
        record=JobService().create(db,Job(external_id="feedback-1",source="test",company="Acme",title="Data Scientist",apply_url="https://example.com/f/apply",source_url="https://example.com/f")); job_id=record.id
    saved=client.post(f"/jobs/{job_id}/feedback",json={"human_label":"excellent","human_notes":"Strong search fit"})
    assert saved.status_code==201 and saved.json()["human_label"]=="excellent"
    assert client.put(f"/jobs/{job_id}/feedback",json={"human_label":"good","human_notes":"Review scope"}).json()["human_label"]=="good"
    assert client.get(f"/jobs/{job_id}").json()["human_label"]=="good"
    assert client.get("/evaluation/ranking").json()["state"]=="insufficient_data"


def test_agent_run_scout_and_fit_execution(monkeypatch):
    scout=ScoutAgent(); jobs=scout.discover(MockConnector(),"mock","Mock AI"); assert len(jobs)==1
    profile=CandidateProfile(skills=[]); prefs=JobPreferences(preferred_titles=["Applied Scientist"])
    result=AgentOrchestrator().dispatch(FitAgent(DeterministicScoringEngine()),jobs[0],profile,prefs); assert 0<=result.overall_score<=100
    with SessionLocal() as db:
        runs=AgentRunService(); record=runs.start(db,"fit","score job",input_state={"external_id":"mock-1"}); completed=runs.complete(db,record,{"overall_score":result.overall_score},[{"action":"score"}]); assert completed.status=="completed"
