from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import select

from app.core.config import Settings
from app.db.database import SessionLocal
from app.db.models import AgentRunRecord, JobRecord, JobSourceRecord, SemanticAnalysisRecord
from app.models.job import Job, RemoteType, ScoreResult
from app.services.candidate_context_service import job_version, current_context
from app.models.profile import JobPreferences
from app.services.career_intelligence_service import CareerIntelligenceService
from app.services.job_service import JobService
from app.services.opportunity_service import OpportunityScoringService
from app.services.scan_orchestrator import ScanOrchestrator
from app.services.discovery_catalog_service import DiscoveryCatalogService
from app.scheduler import Scheduler


def job(external_id="1",score=70,days_old=0):
    return Job(external_id=external_id,source="greenhouse",company="Example Systems",title=f"Machine Learning Engineer {external_id}",location="Metro City",remote_type=RemoteType.hybrid,employment_type="full-time",description=f"Machine learning search ranking Python evaluation role {external_id}",apply_url=f"https://example.test/jobs/{external_id}",source_url=f"https://example.test/jobs/{external_id}",discovered_at=datetime.now(timezone.utc)-timedelta(days=days_old),fit_score=score)


class FixtureConnector:
    def fetch_jobs(self,identifier,company):return [job(str(index)) for index in range(1,6)]


class FixtureSemantic:
    def __init__(self):self.calls=[];self.llm=SimpleNamespace(provider=SimpleNamespace(name="mock",model="mock-fit"))
    def analyze(self,db,job_id):
        self.calls.append(job_id);return SimpleNamespace(report=SimpleNamespace(estimated_cost=.01))


def set_fit(db, record, score):
    service=JobService()
    service.save_score(db, record.id, ScoreResult(overall_score=score,component_scores={},strengths=[],gaps=[],matched_skills=[],missing_skills=[],reasoning_summary="Fictional ranking test",recommendation="strong"))
    row=service.evaluation(db,record.id);row.family_fit_score=score;db.commit()
    db.expire(record,["scores"])


def source(db):
    record=JobSourceRecord(company="Example Systems",ats_type="greenhouse",board_identifier="example",enabled=True);db.add(record);db.commit();return record


def test_semantic_score_is_blended_into_opportunity_score():
    candidate=job(score=60);candidate.semantic_fit_score=100;candidate.semantic_fit_confidence=.9
    result=OpportunityScoringService().score(candidate,JobPreferences(),{"strengths":[{"statement":"Verified ranking alignment","evidence_ids":["E1"]}],"gaps":["A requirement is unknown"]})
    assert result.deterministic_fit==60 and result.semantic_fit==100
    assert result.overall_score>80 and result.why_you_match[0].evidence_ids==["E1"]


def test_semantic_failure_retains_deterministic_opportunity_score():
    result=OpportunityScoringService().score(job(score=60),JobPreferences())
    assert result.semantic_fit is None and result.overall_score>=60


def test_global_ranking_happens_before_pagination():
    db=SessionLocal();service=JobService()
    low=service.create(db,job("low",40));set_fit(db,low,40)
    high=service.create(db,job("high",95,days_old=2));set_fit(db,high,95)
    middle=service.create(db,job("middle",70));set_fit(db,middle,70);db.commit()
    first=service.list(db,limit=1,offset=0);second=service.list(db,limit=1,offset=1)
    assert first.total==3 and first.items[0].external_id=="high" and second.items[0].external_id=="middle";db.close()


def test_persisted_semantic_analysis_drives_job_api_score():
    db=SessionLocal();service=JobService();record=service.create(db,job(score=60));set_fit(db,record,60);db.add(SemanticAnalysisRecord(job_id=record.id,fingerprint="semantic-fixture",deterministic_score=60,semantic_score=90,blended_score=76.5,report_json={"job_version":job_version(record),"confidence":.9,"strengths":[{"statement":"Grounded match","evidence_ids":[next(iter(current_context().evidence_ids))]}],"gaps":[],"requirement_gaps":[]},provider="mock",model="mock-fit",prompt_version="v1",evidence_version="v1"));db.commit()
    result=service.list(db,limit=1).items[0]
    assert result.semantic_fit_score==90 and result.opportunity_score.semantic_fit==90 and result.opportunity_score.why_you_match[0].reason=="Grounded match";db.close()


def test_find_jobs_run_is_bounded_and_independent_of_auto_submit():
    db=SessionLocal();source(db);settings=Settings(llm_enabled=True,llm_provider="mock",llm_model="mock-fit",llm_max_semantic_analyses_per_scan=2,discovery_max_sources_per_run=1,application_mode="manual",auto_submit_enabled=False,candidate_profile_path="../data/profile.example.json",candidate_evidence_path="../data/evidence.example.json",candidate_preferences_path="../data/preferences.example.json")
    semantic=FixtureSemantic();scanner=ScanOrchestrator(connectors={"greenhouse":FixtureConnector});service=CareerIntelligenceService(settings,scanner,semantic)
    run=service.enqueue(db);completed=service.process_next(db);view=service.read(completed)
    assert run.status=="completed" and view.semantic_selected==2 and view.semantic_completed==2 and len(semantic.calls)==2
    assert view.jobs_found==5 and view.ranked_jobs==5 and view.estimated_cost==.02;db.close()


def test_find_jobs_api_queues_without_application_autonomy(client):
    db=SessionLocal();source(db);db.close()
    response=client.post("/career-intelligence/find-jobs")
    assert response.status_code==202 and response.json()["status"]=="queued"
    assert client.get("/career-intelligence/runs/latest").json()["stage"]=="queued"


def test_find_jobs_uses_starter_catalog_without_a_manual_source(client):
    response=client.post("/career-intelligence/find-jobs")
    assert response.status_code==202 and response.json()["source_count"]>0


def test_manual_source_is_prioritized_ahead_of_starter_catalog(tmp_path):
    catalog=tmp_path/"catalog.json";catalog.write_text('[{"company":"Starter One","ats_type":"greenhouse","board_identifier":"starter","domains":["data"],"locations":[]}]')
    db=SessionLocal();manual=JobSourceRecord(company="Requested Company",ats_type="greenhouse",board_identifier="requested",enabled=True,configuration={"origin":"user"});db.add(manual);db.commit()
    selected=DiscoveryCatalogService(Settings(starter_discovery_catalog_path=str(catalog),discovery_max_sources_per_run=2)).select(db,JobPreferences(preferred_domains=["data"]))
    assert [item.company for item in selected]==["Requested Company","Starter One"]
    db.close()


def test_dashboard_diversification_preserves_raw_score_order(monkeypatch):
    db=SessionLocal();service=JobService()
    jobs=[]
    for external,company,score in (("a1","Company A",94),("a2","Company A",93),("b1","Company B",91),("c1","Company C",90)):
        item=job(external,score);item.company=company;record=service.create(db,item);set_fit(db,record,score);jobs.append(record)
    db.commit();monkeypatch.setattr("app.services.job_service.get_settings",lambda:Settings(dashboard_max_jobs_per_company=1))
    raw=service.list(db,limit=10,diversified=False);visible=service.list(db,limit=10,diversified=True)
    assert [x.external_id for x in raw.items]==["a1","a2","b1","c1"]
    assert [x.external_id for x in visible.items]==["a1","b1","c1"]
    assert raw.items[0].opportunity_score.overall_score==visible.items[0].opportunity_score.overall_score
    db.close()


def test_new_jobs_are_selected_before_already_analyzed_jobs():
    db=SessionLocal();source(db);service=JobService()
    analyzed=service.create(db,job("analyzed",99));set_fit(db,analyzed,99)
    fresh=service.create(db,job("fresh",70));set_fit(db,fresh,70)
    db.add(SemanticAnalysisRecord(job_id=analyzed.id,fingerprint="old",semantic_score=99,report_json={"job_version":job_version(analyzed)},provider="mock",model="mock",prompt_version="v1",evidence_version="v1"));db.commit()
    settings=Settings(llm_enabled=True,llm_provider="mock",llm_model="mock",llm_max_semantic_analyses_per_scan=1,candidate_profile_path="../data/profile.example.json",candidate_evidence_path="../data/evidence.example.json",candidate_preferences_path="../data/preferences.example.json")
    semantic=FixtureSemantic();service=CareerIntelligenceService(settings,semantic=semantic);service.enqueue(db,scan_required=False);service.process_next(db)
    assert semantic.calls==[fresh.id];db.close()


def test_progress_reports_real_stages_and_semantic_failure_fallback():
    class FailingSemantic(FixtureSemantic):
        def analyze(self,db,job_id):raise TimeoutError
    db=SessionLocal();source(db);record=JobService().create(db,job("fallback",72));set_fit(db,record,72);db.commit()
    settings=Settings(llm_enabled=True,llm_provider="mock",llm_model="mock",llm_max_semantic_analyses_per_scan=1,candidate_profile_path="../data/profile.example.json",candidate_evidence_path="../data/evidence.example.json",candidate_preferences_path="../data/preferences.example.json")
    service=CareerIntelligenceService(settings,semantic=FailingSemantic());service.enqueue(db,scan_required=False);completed=service.process_next(db);view=service.read(completed)
    assert view.status=="completed" and view.semantic_failed==1 and completed.output_state_json["deterministic_fallback"] is True
    assert [item["stage"] for item in completed.actions_json]==["queued","evaluating_fit","semantic_analysis","semantic_analysis","ranking","completed"]
    db.close()


def test_all_source_failures_are_actionable_and_do_not_claim_results_are_ready():
    class FailingConnector:
        def fetch_jobs(self,identifier,company):raise TimeoutError("fixture source unavailable")
    db=SessionLocal();source(db)
    configured=Settings(llm_enabled=False,discovery_max_sources_per_run=1,candidate_profile_path="../data/profile.example.json",candidate_evidence_path="../data/evidence.example.json",candidate_preferences_path="../data/preferences.example.json")
    service=CareerIntelligenceService(configured,scanner=ScanOrchestrator(connectors={"greenhouse":FailingConnector}))
    service.enqueue(db);failed=service.process_next(db);view=service.read(failed)
    assert view.status=="failed" and view.sources_succeeded==0 and view.sources_failed==1
    assert "No job sources could be reached" in view.message and view.ranked_jobs==0
    db.close()


def test_scheduled_intelligence_is_independent_of_auto_submit(monkeypatch):
    db=SessionLocal();source(db);queued=[]
    monkeypatch.setattr("app.scheduler.ScanOrchestrator.scan",lambda self,db,sources:SimpleNamespace(id=17))
    monkeypatch.setattr("app.scheduler.CareerIntelligenceService.enqueue",lambda self,db,**kwargs:queued.append(kwargs))
    monkeypatch.setattr("app.scheduler.AutonomyPipelineService.run",lambda *args:(_ for _ in ()).throw(AssertionError("application autonomy must remain separate")))
    monkeypatch.setattr("app.scheduler.get_settings",lambda:Settings(application_mode="manual",auto_submit_enabled=False,discovery_interval_minutes=60,morning_report_hour_local=23))
    actions=Scheduler("fixture-scheduler").tick(db,datetime(2026,9,5,12,tzinfo=timezone.utc))
    assert actions==["DISCOVERY","CAREER_INTELLIGENCE_QUEUED"]
    assert queued==[{"trigger":"scheduled","scan_required":False,"scan_id":17}]
    db.close()


def test_scheduler_restart_does_not_repeat_a_recent_scan(monkeypatch):
    from app.db.models import ScanRunRecord
    db=SessionLocal();source(db);now=datetime(2026,9,5,12,tzinfo=timezone.utc)
    db.add(ScanRunRecord(status="completed",started_at=now-timedelta(minutes=2),completed_at=now-timedelta(minutes=1)));db.commit()
    monkeypatch.setattr("app.scheduler.get_settings",lambda:Settings(discovery_interval_minutes=60,morning_report_hour_local=23))
    monkeypatch.setattr("app.scheduler.ScanOrchestrator.scan",lambda *args:(_ for _ in ()).throw(AssertionError("recent scan must be reused")))
    actions=Scheduler("restarted-scheduler").tick(db,now)
    assert "DISCOVERY" not in actions and "CAREER_INTELLIGENCE_QUEUED" not in actions
    db.close()


def test_scheduler_restart_accepts_recent_partial_scan(monkeypatch):
    from app.db.models import ScanRunRecord
    db=SessionLocal();now=datetime(2026,9,5,12,tzinfo=timezone.utc)
    db.add(ScanRunRecord(status="completed_with_errors",started_at=now-timedelta(minutes=2),completed_at=now-timedelta(minutes=1)));db.commit()
    monkeypatch.setattr("app.scheduler.get_settings",lambda:Settings(discovery_interval_minutes=60,morning_report_hour_local=23))
    monkeypatch.setattr("app.scheduler.ScanOrchestrator.scan",lambda *args:(_ for _ in ()).throw(AssertionError("recent partial scan must be reused")))
    assert "DISCOVERY" not in Scheduler("partial-scan-restart").tick(db,now)
    db.close()
