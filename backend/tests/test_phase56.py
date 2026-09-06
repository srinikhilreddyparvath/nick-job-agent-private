from pathlib import Path
from types import SimpleNamespace

import pytest
from playwright.sync_api import sync_playwright

from app.agents.browser import BrowserAgent
from app.models.browser import ApplicationFormField, BrowserMode, BrowserRunRequest, Eligibility, FieldType
from app.services.application_eligibility import ApplicationEligibilityPolicy
from app.services.ats_form_adapters import adapter_for
from app.services.browser_service import BrowserService
from app.services.field_mapping_service import FieldMappingService
from app.db.models import ApplicationEventRecord,ApplicationFormRecord,ApplicationRecord,BrowserApplicationEventRecord
from app.services.browser_orchestrator import classify_submission_failure
from app.services.submission_state_service import SubmissionStateService

FIXTURES=Path(__file__).parent/"fixtures"

def job(score=64, family="RESEARCH_AI"):
    return SimpleNamespace(id=9,company="Example",title="Research Engineer",fit_score=score,family_fit_score=score,role_family=family)

def package(tmp_path=None,status="APPROVED"):
    path=None
    if tmp_path:
        path=tmp_path/"resume.pdf";path.write_bytes(b"%PDF-1.4 test")
    return SimpleNamespace(status=status,tailored_resume_path=str(path) if path else None,application_answers=[])

def field(label,required=True,kind=FieldType.text,options=None,limit=None):
    return ApplicationFormField(field_id="f",label=label,normalized_label="",field_type=kind,required=required,options=options or [],character_limit=limit)

def test_moderate_fit_is_eligible():
    result=ApplicationEligibilityPolicy().evaluate(job(),package())
    assert result.eligibility==Eligibility.eligible

def test_low_fit_relevant_role_remains_eligible():
    assert ApplicationEligibilityPolicy().evaluate(job(42),package()).eligibility==Eligibility.eligible_low_confidence

def test_apply_anyway_overrides_fit_not_hard_blocker():
    policy=ApplicationEligibilityPolicy()
    assert policy.evaluate(job(10,"UNKNOWN"),manual_override=True).eligibility==Eligibility.eligible
    assert policy.evaluate(job(90),manual_override=True,hard_blockers=["BLOCKED_CAPTCHA"]).eligibility==Eligibility.blocked

def test_browser_agent_permissions_and_separate_submit():
    definition=BrowserAgent().definition
    assert definition.active is True
    assert "inspect_form" in definition.allowed_tools
    assert "submit_application" in definition.allowed_tools
    assert "separately authorized submit" in definition.allowed_actions

@pytest.mark.parametrize(("label","value"),[("Given Name","Alex"),("Surname","Morgan"),("Preferred Name","Alex"),("Email","alex.morgan@example.com"),("Phone","+1 (555) 010-0142"),("Portfolio","https://example.com/portfolio")])
def test_canonical_field_mapping(label,value):
    mapped=FieldMappingService().map(field(label))
    assert mapped.mapped_answer==value and mapped.write_allowed

def test_middle_name_and_unknown_sensitive_handling():
    mapper=FieldMappingService()
    required=mapper.map(field("Middle Name",True));optional=mapper.map(field("Middle Name",False))
    assert required.requires_human_review and required.mapped_answer is None
    assert optional.mapped_answer is None and not optional.write_allowed
    assert mapper.map(field("Current salary",True)).requires_human_review

def test_work_authorization_and_voluntary_demographic():
    mapper=FieldMappingService()
    assert mapper.map(field("Will you now or in the future require employment visa sponsorship?")).mapped_answer=="YES"
    demographic=mapper.map(field("Veteran Status",False,FieldType.select,["Veteran","Decline to answer"]))
    assert demographic.mapped_answer=="I am not a protected veteran" and demographic.write_allowed

def test_character_limit_blocks_write():
    mapped=FieldMappingService().map(field("Full Legal Name",True,limit=5))
    assert not FieldMappingService().validate_write(mapped)

@pytest.mark.parametrize(("url","ats"),[("https://jobs.ashbyhq.com/acme/1","ashby"),("https://boards.greenhouse.io/acme/jobs/1","greenhouse"),("https://jobs.lever.co/acme/1","lever"),("https://example.com/apply","generic")])
def test_ats_adapters(url,ats): assert adapter_for(url).ats==ats

def test_playwright_fixture_inspection_mapping_and_upload(tmp_path):
    service=BrowserService();html=(FIXTURES/"ashby_form.html").read_text();pkg=package(tmp_path)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_content(html)
        schema=service.inspect_page(page,job(),pkg)
        assert len(schema.fields)==7 and len(schema.required_fields)==6
        assert next(x for x in schema.fields if x.label=="Phone").field_type==FieldType.phone
        assert next(x for x in schema.fields if x.label=="Resume").mapped_answer_source=="Approved ApplicationPackage artifact"
        resolved,blockers,events=service.fill_page(page,schema,pkg,upload_resume=True)
        # Optional middle name is intentionally blank; all six safe values,
        # including the approved resume upload, are resolved.
        assert not blockers and resolved==6 and any(x["event"]=="FILE_UPLOADED" for x in events)
        assert page.locator("#first").input_value()=="Alex"
        browser.close()

def test_greenhouse_and_lever_fixture_safety():
    service=BrowserService()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        green=browser.new_page();green.set_content((FIXTURES/"greenhouse_form.html").read_text());gs=service.inspect_page(green,job(),package());assert all(service.mapper.validate_write(x) for x in gs.fields)
        lever=browser.new_page();lever.set_content((FIXTURES/"lever_form.html").read_text());ls=service.inspect_page(lever,job(),package());assert sum(x.requires_human_review for x in ls.fields)==2
        browser.close()

def test_captcha_auth_and_submission_verification():
    service=BrowserService()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_content("<title>x</title><input type=password><iframe src='captcha'></iframe>")
        schema=service.inspect_page(page,job(),package());assert schema.captcha_detected and schema.authentication_required
        ok,meta=service.verify_submission(page,page.url);assert not ok and meta["confirmation_url"] is None
        page.set_content("<body>Thank you for applying</body>");assert service.verify_submission(page,page.url)[0]
        browser.close()

def test_hidden_captcha_and_optional_write_failure_do_not_block():
    service=BrowserService()
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_content("<iframe src='captcha' style='display:none'></iframe><input id='name' aria-label='Full Name' required><input id='hidden-file' type='file' style='display:none'>")
        schema=service.inspect_page(page,job(),package());assert not schema.captcha_detected
        resolved,blockers,events=service.fill_page(page,schema,package(),upload_resume=True)
        assert not blockers and resolved==1
        browser.close()

def test_default_settings_keep_auto_submit_off(client):
    response=client.get("/application-settings")
    assert response.status_code==200
    assert response.json()["auto_submit_enabled"] is False
    assert response.json()["application_mode"]=="manual"

def test_no_real_submission_in_fixture_suite():
    request=BrowserRunRequest(mode=BrowserMode.fill_only,dry_run=True)
    assert request.dry_run and request.mode==BrowserMode.fill_only

def test_timeout_boundary_distinguishes_safe_retry_from_uncertain_submission():
    assert classify_submission_failure("LOCATE_SUBMIT_CONTROL",False,"TimeoutError")=="SUBMISSION_TIMEOUT"
    assert classify_submission_failure("CLICK_SUBMIT_CONTROL",True,"TimeoutError")=="SUBMISSION_UNVERIFIED"
    assert classify_submission_failure("WAIT_FOR_CONFIRMATION",True,"TimeoutError")=="SUBMISSION_UNVERIFIED"

def test_crash_after_click_reconciles_without_retry(client):
    job=client.post("/jobs/ingest-text",json={"source_url":"https://fixture.invalid/crash","company":"Crash Fixture","title":"Research Engineer","location":"Remote US","job_description_text":"Machine learning research."}).json()["job"]
    from app.db.database import SessionLocal
    with SessionLocal() as db:
        db.add(BrowserApplicationEventRecord(job_id=job["id"],event_type="SUBMIT_CLICK_STARTED",details_json={"external_click_occurred":False}));db.add(BrowserApplicationEventRecord(job_id=job["id"],event_type="SUBMIT_CLICKED",details_json={"external_click_occurred":True}));db.commit()
        application=SubmissionStateService().reconcile(db,job["id"])
        assert application.status=="SUBMISSION_UNVERIFIED" and SubmissionStateService().lockout_reason(db,job["id"])=="SUBMISSION_UNVERIFIED"
        assert db.query(ApplicationEventRecord).filter_by(application_id=application.id,to_status="SUBMISSION_UNVERIFIED").count()==1

def test_persisted_complete_form_has_one_ready_state(client):
    schema={"application_url":"https://fixture.invalid/apply","ats":"ashby","company":"Fixture","job_id":1,"fields":[{"field_id":"name","label":"Full Name","normalized_label":"full name","field_type":"text","required":True,"write_allowed":True,"requires_human_review":False}],"required_fields":["name"],"submit_controls":[{"selector_strategy":"role_and_accessible_name","accessible_name":"Submit application","element_type":"button","visible":True,"enabled":True,"actionable":True}],"captcha_detected":False,"authentication_required":False}
    from app.db.database import SessionLocal
    with SessionLocal() as db:
        db.add(ApplicationFormRecord(job_id=1,application_url=schema["application_url"],ats="ashby",schema_json=schema,form_fingerprint="fixture",status="INSPECTED"));db.commit()
    response=client.get("/jobs/1/application-form")
    assert response.status_code==200 and response.json()["status"]=="READY_TO_SUBMIT"

def test_empty_submit_controls_never_ready(client):
    schema={"application_url":"https://fixture.invalid/apply","ats":"ashby","company":"Fixture","job_id":1,"fields":[{"field_id":"name","label":"Full Name","normalized_label":"full name","field_type":"text","required":True,"write_allowed":True,"requires_human_review":False}],"required_fields":["name"],"submit_controls":[],"captcha_detected":False,"authentication_required":False,"status":"READY_TO_SUBMIT"}
    from app.db.database import SessionLocal
    with SessionLocal() as db:
        db.add(ApplicationFormRecord(job_id=1,application_url=schema["application_url"],ats="ashby",schema_json=schema,form_fingerprint="fixture",status="READY_TO_SUBMIT"));db.commit()
    response=client.get("/jobs/1/application-form")
    assert response.status_code==200 and response.json()["status"]=="SUBMIT_CONTROL_NOT_FOUND"

def test_ashby_submit_detection_ignores_upload_and_groups_radios():
    service=BrowserService();html="""<form><fieldset><legend>Are you based in San Francisco or open to relocating?</legend><label><input type=radio name=location>San Francisco based</label><label><input type=radio name=location>Open to relocating</label></fieldset><button type=submit>Upload File</button><button type=button>Cancel</button><button type=submit>Submit Application</button></form>"""
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True);page=browser.new_page();page.set_content(html);schema=service.inspect_page(page,job(),package())
        assert len(schema.submit_controls)==1 and schema.submit_controls[0].accessible_name=="Submit Application" and schema.submit_controls[0].actionable
        radios=[item for item in schema.fields if item.field_type==FieldType.radio]
        assert len(radios)==1 and radios[0].label=="Are you based in San Francisco or open to relocating?"
        assert radios[0].options==["San Francisco based","Open to relocating"] and not radios[0].required and not radios[0].write_allowed
        browser.close()

def test_failed_form_status_never_becomes_ready_by_field_fallback(client):
    schema={"application_url":"https://fixture.invalid/apply","ats":"ashby","company":"Fixture","job_id":1,"fields":[{"field_id":"name","label":"Full Name","normalized_label":"full name","field_type":"text","required":True,"write_allowed":True,"requires_human_review":False}],"required_fields":["name"],"captcha_detected":False,"authentication_required":False}
    from app.db.database import SessionLocal
    with SessionLocal() as db:
        db.add(ApplicationFormRecord(job_id=1,application_url=schema["application_url"],ats="ashby",schema_json=schema,form_fingerprint="fixture",status="FAILED"));db.commit()
    response=client.get("/jobs/1/application-form")
    assert response.status_code==200 and response.json()["status"]=="FAILED"
