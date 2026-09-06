from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from app.core.config import Settings
from app.db.database import SessionLocal
from app.db.models import ApplicationQueueItemRecord,RuntimeHeartbeatRecord
from app.models.browser import ApplicationFormField,FieldType
from app.services.artifact_storage import LocalArtifactStorage
from app.services.field_mapping_service import FieldMappingService
from app.services.morning_report_service import MorningReportService
from app.services.outcome_service import OutcomeService
from app.services.policy_service import AnswerBankService,AvailabilityPolicy,StandingApplicationPolicy,WorkAuthorizationService
from app.services.runtime_service import QueueLeaseService,RuntimeControlService
from app.services.web_discovery import DiscoveryLead,MockWebJobDiscoveryProvider,WebDiscoveryService

def f(label,required=True):return ApplicationFormField(field_id=label,label=label,normalized_label="",field_type=FieldType.text,required=required)

def test_h1b_expiration_composite_mapping():
 result=WorkAuthorizationService().assess("Do you require Visa sponsorship? If so which one, and when does your Visa expire?")
 assert result.answer=="Example Work Visa; expiration 12/31/2030" and not result.requires_human_review

def test_dynamic_start_date_month_and_notice():
 policy=AvailabilityPolicy();reference=date(2026,9,2)
 assert policy.answer("Earliest Start Date",reference).answer=="2026-09-16"
 assert policy.answer("Earliest Start Month",reference).answer=="September 2026"
 assert policy.answer("Notice Period",reference).answer=="2 weeks"
 assert policy.answer("When can you start?",reference).calculated_start_date==date(2026,9,16)

def test_full_name_and_middle_name_policy():
 mapper=FieldMappingService(date(2026,9,2));full=mapper.map(f("Full Name"));middle=mapper.map(f("Middle Name"))
 assert full.mapped_answer=="Alex Morgan" and full.write_allowed
 assert middle.requires_human_review and middle.mapped_answer is None

def test_exa_new_policy_resolution_without_guessing():
 mapper=FieldMappingService(date(2026,9,2))
 labels=["Full Name","Earliest month you'd be able to join","Do you require Visa sponsorship to work in your selected location? If so, which one? And when does your Visa expire?"]
 mapped=[mapper.map(f(x)) for x in labels]
 assert [x.mapped_answer for x in mapped]==["Alex Morgan","September 2026","Example Work Visa; expiration 12/31/2030"]
 assert mapper.map(f("How did you hear about Example AI?")).mapped_answer=="LinkedIn"

def test_discovery_source_preference_and_referral_safeguard():
 policy=StandingApplicationPolicy()
 assert policy.discovery_source("How did you hear about us?",["Other","Google Search","Social Media","LinkedIn"])[0]=="LinkedIn"
 assert policy.discovery_source("How did you hear about us?",["Other","Social Network"])[0]=="Social Network"
 assert policy.discovery_source("Employee referral name",["Employee Referral","Other"])[0] is None

def test_motivation_policy_and_answer_bank_metadata():
 mapper=FieldMappingService(date(2026,9,2));mapped=mapper.map(f("What motivates you?"))
 assert mapped.write_allowed and "research and evaluation" in mapped.mapped_answer
 short=ApplicationFormField(field_id="m",label="What motivates you?",normalized_label="",field_type=FieldType.textarea,required=True,character_limit=150)
 assert len(mapper.map(short).mapped_answer)<=150
 answers={x.id:x for x in AnswerBankService().all()["approved_structured"]}
 assert answers["DISCOVERY_SOURCE_GENERIC"].scope=="REUSABLE"
 assert answers["PROFESSIONAL_MOTIVATION"].approval_source=="EXAMPLE_PROFILE"

def test_queue_claim_is_exclusive_and_stale_lease_recovers():
 db=SessionLocal();row=ApplicationQueueItemRecord(job_id=1,application_package_id=1,priority=5,eligibility="ELIGIBLE",status="QUEUED");db.add(row);db.commit();leases=QueueLeaseService();claimed=leases.claim(db,"one",10);assert claimed.lease_owner=="one" and leases.claim(db,"two",10) is None
 claimed.lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1);db.commit();assert leases.recover(db)==1 and claimed.status=="RETRYABLE";db.close()

def test_submit_started_crash_requires_verification():
 db=SessionLocal();row=ApplicationQueueItemRecord(job_id=2,application_package_id=2,priority=5,eligibility="ELIGIBLE",status="SUBMITTING",lease_owner="dead",lease_expires_at=datetime.now(timezone.utc)-timedelta(seconds=1),submit_started_at=datetime.now(timezone.utc));db.add(row);db.commit();QueueLeaseService().recover(db);assert row.status=="NEEDS_REVIEW" and row.block_reason=="SUBMISSION_UNVERIFIED";db.close()

def test_heartbeat_pause_and_kill_switch():
 db=SessionLocal();runtime=RuntimeControlService();runtime.heartbeat(db,"worker","test",success=True);assert db.get(RuntimeHeartbeatRecord,"worker").last_success_at;runtime.set(db,"AUTO_APPLY_PAUSED",True);assert runtime.paused(db);db.close()

def test_auto_submit_requires_verified_receipt(client):
 response=client.patch("/application-settings",json={"auto_submit_enabled":True})
 assert response.status_code==409 and response.json()["detail"]=="FIRST_VERIFIED_RECEIPT_REQUIRED"

def test_web_discovery_is_bounded_and_leads_unverified():
 leads=[DiscoveryLead(f"https://employer.test/{i}") for i in range(5)];settings=Settings(web_discovery_enabled=True,web_discovery_queries_per_run=1,web_discovery_max_urls_per_run=2);result=WebDiscoveryService(MockWebJobDiscoveryProvider(leads),settings).run(["one","two"]);assert len(result["leads"])==2 and result["requires_url_verification"]

def test_web_discovery_disabled_by_default():assert WebDiscoveryService().run(["query"])["status"]=="disabled"

def test_artifact_storage_confines_and_hashes(tmp_path):
 source=tmp_path/"resume.pdf";source.write_bytes(b"resume");store=LocalArtifactStorage(tmp_path/"artifacts");digest=store.put("jobs/1/resume.pdf",source);assert len(digest)==64 and store.path("jobs/1/resume.pdf").exists()
 try:store.path("../escape")
 except ValueError:pass
 else:assert False

def test_morning_report_and_outcome_insufficient_data():
 db=SessionLocal();report=MorningReportService().generate(db);assert "jobs_discovered" in report.metrics_json;assert OutcomeService().metrics(db)["status"]=="insufficient_data";db.close()
