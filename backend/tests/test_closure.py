from playwright.sync_api import sync_playwright

from app.db.database import SessionLocal
from app.db.models import ApplicationEventRecord,ApplicationReceiptRecord,ApplicationRecord,BrowserApplicationEventRecord
from app.models.browser import BrowserMode, BrowserRunRequest
from app.services.browser_orchestrator import BrowserOrchestrator
from app.services.morning_report_service import MorningReportService
from app.services.outcome_service import OutcomeService


def test_complete_mock_application_lifecycle(client):
    job=client.post("/jobs/ingest-text",json={"source_url":"https://fixture.invalid/jobs/closure","company":"Closure Fixture Lab","title":"Research Engineer","location":"San Francisco, CA","job_description_text":"Build and evaluate Python machine-learning research systems with cross-functional partners."}).json()["job"]
    assert client.post(f"/jobs/{job['id']}/analyze",json={"use_mock":True}).status_code==200
    assert client.post(f"/jobs/{job['id']}/research",json={"use_mock":True}).status_code==200
    package=client.post(f"/jobs/{job['id']}/application-package",json={"use_mock":True,"questions":[]}).json()
    assert package["status"]=="REVIEW_REQUIRED"
    reviewed=client.post(f"/jobs/{job['id']}/application-package/review?use_mock=true").json();assert reviewed["status"]=="READY_FOR_REVIEW"
    assert client.post(f"/jobs/{job['id']}/application-package/approve",json={}).json()["status"]=="APPROVED"
    html="""<form><label>Full Name<input id='full' required></label><label>Email<input id='email' type='email' required></label><label>Will you now or in the future require employment visa sponsorship?<input id='visa' required></label><button type='submit'>Submit</button></form><script>document.querySelector('form').onsubmit=(e)=>{e.preventDefault();document.body.innerHTML='Thank you for applying'}</script>"""
    with SessionLocal() as db, sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_content(html)
        result=BrowserOrchestrator().run(db,job["id"],BrowserRunRequest(mode=BrowserMode.user_triggered_submit,dry_run=False),page=page)
        assert result.submitted and result.status=="SUBMITTED" and result.confirmation_verified and result.receipt_created and db.query(ApplicationReceiptRecord).filter_by(job_id=job["id"]).count()==1
        assert db.query(ApplicationRecord).filter_by(job_id=job["id"]).one().status=="SUBMITTED"
        assert db.query(ApplicationEventRecord).filter_by(to_status="SUBMITTED").count()==1
        second=BrowserOrchestrator().run(db,job["id"],BrowserRunRequest(mode=BrowserMode.user_triggered_submit,dry_run=False),page=page)
        assert second.status=="ALREADY_SUBMITTED" and not second.retry_allowed
        outcome=OutcomeService().record(db,job["id"],"SUBMITTED");assert outcome.application_receipt_id is not None
        report=MorningReportService().generate(db);assert report.metrics_json["applications_submitted"]>=1
        browser.close()

def test_click_without_confirmation_is_canonical_unverified_and_locked(client):
    job=client.post("/jobs/ingest-text",json={"source_url":"https://fixture.invalid/jobs/unverified","company":"Unverified Fixture","title":"Research Engineer","location":"San Francisco, CA","job_description_text":"Build and evaluate machine learning systems."}).json()["job"]
    client.post(f"/jobs/{job['id']}/analyze",json={"use_mock":True});client.post(f"/jobs/{job['id']}/research",json={"use_mock":True});client.post(f"/jobs/{job['id']}/application-package",json={"use_mock":True,"questions":[]});client.post(f"/jobs/{job['id']}/application-package/review?use_mock=true");client.post(f"/jobs/{job['id']}/application-package/approve",json={})
    html="""<form><label>Full Name<input id='full' required></label><label>Email<input id='email' type='email' required></label><label>Will you now or in the future require employment visa sponsorship?<input id='visa' required></label><button type='submit'>Submit Application</button></form><script>document.querySelector('form').onsubmit=(e)=>e.preventDefault()</script>"""
    with SessionLocal() as db, sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_content(html)
        result=BrowserOrchestrator().run(db,job["id"],BrowserRunRequest(mode=BrowserMode.user_triggered_submit,dry_run=False),page=page)
        assert result.status=="SUBMISSION_UNVERIFIED" and result.external_click_occurred and not result.confirmation_verified and not result.receipt_created and not result.retry_allowed
        assert db.query(ApplicationRecord).filter_by(job_id=job["id"]).one().status=="SUBMISSION_UNVERIFIED"
        assert db.query(ApplicationEventRecord).filter_by(to_status="SUBMISSION_UNVERIFIED").count()==1
        assert db.query(ApplicationReceiptRecord).filter_by(job_id=job["id"]).count()==0
        submission_events={"SUBMIT_CLICK_STARTED","SUBMIT_CLICKED","SUBMISSION_UNVERIFIED"}
        assert [x.event_type for x in db.query(BrowserApplicationEventRecord).filter_by(job_id=job["id"]).all() if x.event_type in submission_events]==["SUBMIT_CLICK_STARTED","SUBMIT_CLICKED","SUBMISSION_UNVERIFIED"]
        second=BrowserOrchestrator().run(db,job["id"],BrowserRunRequest(mode=BrowserMode.user_triggered_submit,dry_run=False),page=page)
        assert second.status=="SUBMISSION_UNVERIFIED" and not second.retry_allowed
        browser.close()
