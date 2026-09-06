import hashlib,re,time
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select
from app.core.config import get_settings
from app.db.models import ApplicationFormRecord,ApplicationQueueItemRecord,ApplicationReceiptRecord,BrowserApplicationEventRecord,JobRecord
from app.models.browser import BrowserRunResult
from app.services.application_eligibility import ApplicationEligibilityPolicy
from app.services.application_package_service import ApplicationPackageService
from app.services.browser_service import BrowserService
from app.services.job_service import JobService
from app.services.llm_service import configured_llm_service
from app.services.runtime_service import RuntimeControlService
from app.services.field_mapping_service import FieldMappingService
from app.services.submission_state_service import SubmissionStateService

def classify_submission_failure(stage,external_click_occurred,exception_name):
 if external_click_occurred or stage in {"CLICK_SUBMIT_CONTROL","WAIT_FOR_CONFIRMATION","VERIFY_RECEIPT"}:return "SUBMISSION_UNVERIFIED"
 return "SUBMISSION_TIMEOUT" if exception_name=="TimeoutError" else "SUBMISSION_FAILED"

class BrowserOrchestrator:
 def __init__(self,browser_service=None):self.browser=browser_service or BrowserService();self.settings=get_settings();self.eligibility=ApplicationEligibilityPolicy()
 def package(self,db,job_id):
  try:return ApplicationPackageService(configured_llm_service(use_mock=True)).get(db,job_id)
  except Exception:return None
 def decision(self,db,job_id,manual_override=False):
  job=db.get(JobRecord,job_id);package=self.package(db,job_id)
  if not job:return None
  blockers=[] if package and package.status in {"READY_FOR_REVIEW","APPROVED"} else ["PACKAGE_REVIEW_NOT_PASSED" if package else "MISSING_APPLICATION_PACKAGE"]
  return self.eligibility.evaluate(JobService().to_schema(job),package,manual_override=manual_override,hard_blockers=blockers)
 def run(self,db,job_id,request,page=None):
  job=db.get(JobRecord,job_id);package=self.package(db,job_id)
  if not job:return BrowserRunResult(status="FAILED",blockers=["JOB_NOT_FOUND"])
  decision=self.decision(db,job_id,request.manual_override)
  if decision.eligibility=="BLOCKED":return BrowserRunResult(status="BLOCKED",eligibility=decision,blockers=decision.hard_blockers)
  submission_state=SubmissionStateService()
  if request.mode in {"USER_TRIGGERED_SUBMIT","AUTO_SUBMIT"} and not request.dry_run:
   submission_state.reconcile(db,job_id)
   lockout=submission_state.lockout_reason(db,job_id)
   if lockout:return BrowserRunResult(status=lockout,eligibility=decision,blockers=[lockout],retry_allowed=False)
  owns=False;runtime=None;browser=None;stage="NAVIGATE_APPLICATION";started=time.monotonic();external_click=False;schema=None;form=None;control_count=0
  try:
   if page is None:
    from playwright.sync_api import sync_playwright
    runtime=sync_playwright().start();browser=runtime.chromium.launch(headless=self.settings.browser_headless);page=browser.new_page();owns=True
    page.goto(job.apply_url,wait_until="domcontentloaded",timeout=int(self.settings.browser_timeout_seconds*1000));stage="WAIT_FOR_FORM";page.wait_for_load_state("networkidle",timeout=int(self.settings.browser_timeout_seconds*1000))
   if page.locator("input,textarea,select").count()==0:
    buttons=page.get_by_role("button",name=re.compile("apply",re.I));links=page.get_by_role("link",name=re.compile("apply",re.I));apply=next((buttons.nth(i) for i in range(buttons.count()) if buttons.nth(i).is_visible()),None)
    if apply is None:apply=next((links.nth(i) for i in range(links.count()) if links.nth(i).is_visible()),None)
    if apply:apply.click();page.locator("input,textarea,select").first.wait_for(timeout=int(self.settings.browser_timeout_seconds*1000))
   stage="VERIFY_FORM";schema=self.browser.inspect_page(page,JobService().to_schema(job),package);control_count=len(self.browser.actionable_submit_controls(schema));controls=RuntimeControlService()
   for field in schema.fields:
    normalized=FieldMappingService().normalize(field.label);saved=controls.get(db,f"FORM_ANSWER:{job_id}:{normalized}",None) or controls.get(db,f"STANDING_ANSWER:{normalized}",None)
    if saved is not None:field.mapped_answer=saved;field.mapped_answer_source="User-approved resolution";field.requires_human_review=False;field.write_allowed=True;field.confidence=1
   form=db.scalar(select(ApplicationFormRecord).where(ApplicationFormRecord.job_id==job_id)) or ApplicationFormRecord(job_id=job_id,application_url=schema.application_url,ats=schema.ats,schema_json={},form_fingerprint=schema.form_fingerprint)
   form.application_url=schema.application_url;form.ats=schema.ats;form.form_fingerprint=schema.form_fingerprint;form.manual_application_override=request.manual_override;db.add(form)
   self.event(db,job_id,"FORM_INSPECTED",details={"ats":schema.ats,"field_count":len(schema.fields),"captcha":schema.captcha_detected,"auth":schema.authentication_required,"submit_control_count":control_count});db.flush()
   blockers=self.browser.readiness_blockers(schema,package,decision);events=[{"event":"FORM_INSPECTED","ats":schema.ats,"fields":len(schema.fields),"submit_control_count":control_count}]
   resolved=sum(1 for x in schema.fields if self.browser.mapper.validate_write(x));needs=sum(1 for x in schema.fields if x.required and not self.browser.mapper.validate_write(x));upload="NOT_ATTEMPTED"
   non_control_blockers=[x for x in blockers if x!="SUBMIT_CONTROL_NOT_FOUND"]
   if request.mode!="INSPECT_ONLY" and not non_control_blockers:
    stage="REFILL_IF_NEEDED";resolved,write_blockers,write_events=self.browser.fill_page(page,schema,package,upload_resume=self.settings.browser_upload_in_dry_run or not request.dry_run);blockers+=write_blockers;events+=write_events;upload="UPLOADED" if any(x.get("event")=="FILE_UPLOADED" for x in events) else "SKIPPED_NOT_APPROVED_OR_DISABLED"
    for item in write_events:self.event(db,job_id,item["event"],item.get("category"),{k:v for k,v in item.items() if k not in {"event","category"}})
    db.commit()
   blockers=list(dict.fromkeys(blockers));ready=not blockers;submitted=False;confirmation=None
   if request.mode in {"USER_TRIGGERED_SUBMIT","AUTO_SUBMIT"} and not request.dry_run:
    authorized=True
    if request.mode=="AUTO_SUBMIT":
     authorized,reason=controls.auto_submit_allowed(db)
     if not authorized:blockers.append(reason)
    if authorized and not blockers and db.scalar(select(ApplicationReceiptRecord).where(ApplicationReceiptRecord.job_id==job_id)):blockers.append("DUPLICATE_APPLICATION")
    if authorized and not blockers:
     stage="LOCATE_SUBMIT_CONTROL";locator,control=self.browser.locate_submit_control(page,schema)
     if locator is None:blockers.append("SUBMIT_CONTROL_NOT_FOUND")
     elif not locator.is_visible() or not locator.is_enabled():stage="VERIFY_SUBMIT_CONTROL";blockers.append("SUBMIT_CONTROL_NOT_ACTIONABLE")
    if authorized and not blockers:
     queue=db.scalar(select(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.job_id==job_id).order_by(ApplicationQueueItemRecord.created_at.desc()).limit(1))
     if queue:queue.status="SUBMITTING";queue.submit_started_at=datetime.now(timezone.utc)
     self.event(db,job_id,"SUBMIT_CLICK_STARTED",details={"stage":"CLICK_SUBMIT_CONTROL","external_click_occurred":False,"selector_strategy":control.selector_strategy});db.commit();stage="CLICK_SUBMIT_CONTROL";external_click=True
     previous=page.url;locator.click(timeout=int(self.settings.browser_timeout_seconds*1000));self.event(db,job_id,"SUBMIT_CLICKED",details={"external_click_occurred":True});db.commit();stage="WAIT_FOR_CONFIRMATION";page.wait_for_load_state("domcontentloaded",timeout=int(self.settings.browser_timeout_seconds*1000))
     stage="VERIFY_RECEIPT";submitted,meta=self.browser.verify_submission(page,previous,schema.ats);confirmation=meta["confirmation_url"];self.event(db,job_id,"SUBMISSION_CONFIRMED" if submitted else "SUBMISSION_UNVERIFIED",details={"confirmation_url":confirmation,"external_click_occurred":True,"signals":meta.get("signals",[])})
     if submitted:
      application=submission_state.transition(db,job_id,"SUBMITTED","External submission confirmed by provider-specific browser signals.");digest=hashlib.sha256(Path(package.tailored_resume_path).read_bytes()).hexdigest();db.add(ApplicationReceiptRecord(application_id=application.id,job_id=job_id,company=job.company,role=job.title,ats=schema.ats,apply_url=job.apply_url,confirmation_url=confirmation,external_confirmation_text=meta["confirmation_text"],resume_artifact_hash=digest,application_package_version=package.resume_version_id))
     else:submission_state.transition(db,job_id,"SUBMISSION_UNVERIFIED","External submit control was clicked, but confirmation could not be verified. Do not retry until reconciled.");blockers.append("SUBMISSION_UNVERIFIED")
     if queue:queue.status="SUBMITTED" if submitted else "NEEDS_REVIEW";queue.block_reason=None if submitted else "SUBMISSION_UNVERIFIED"
     db.commit()
    if blockers and not external_click:
     canonical="BLOCKED" if any(item.startswith("BLOCKED_") for item in blockers) else "SUBMISSION_FAILED"
     submission_state.transition(db,job_id,canonical,f"Submission stopped before external click: {blockers[0]}.")
     db.commit()
   blockers=list(dict.fromkeys(blockers));ready=ready and not blockers;status="SUBMITTED" if submitted else blockers[0] if blockers else "READY_TO_SUBMIT" if ready else "NEEDS_REVIEW"
   schema.status=status;form.status=status;form.schema_json=schema.model_dump(mode="json");db.add(form);db.commit()
   return BrowserRunResult(status=status,eligibility=decision,form=schema,fields_resolved=resolved,fields_needing_review=needs,resume_upload_status=upload,ready_to_submit=ready,blockers=blockers,events=events,submitted=submitted,confirmation_url=confirmation,external_click_occurred=external_click,confirmation_verified=submitted,receipt_created=submitted,retry_allowed=not external_click,diagnostics={"stage":stage,"submit_control_count":control_count,"elapsed_ms":int((time.monotonic()-started)*1000)})
  except Exception as exc:
   after_click=external_click or stage in {"CLICK_SUBMIT_CONTROL","WAIT_FOR_CONFIRMATION","VERIFY_RECEIPT"};code=classify_submission_failure(stage,external_click,type(exc).__name__);details={"stage":stage,"exception":type(exc).__name__,"message":str(exc)[:300],"url":getattr(page,"url",None),"elapsed_ms":int((time.monotonic()-started)*1000),"external_click_occurred":after_click,"submit_control_count":control_count}
   db.rollback();self.event(db,job_id,code,details=details);submission_state.transition(db,job_id,"SUBMISSION_UNVERIFIED" if after_click else code,"Browser submission failed after external click; confirmation is unknown." if after_click else f"Browser submission failed before external click at {stage}.")
   if form and schema:form.status=code;schema.status=code;form.schema_json=schema.model_dump(mode="json");db.add(form)
   db.commit();return BrowserRunResult(status=code,eligibility=decision,form=schema,blockers=[code],failure_stage=stage,error_code=code,external_click_occurred=after_click,retry_allowed=not after_click,diagnostics=details)
  finally:
   if owns and browser:browser.close()
   if owns and runtime:runtime.stop()
 def event(self,db,job_id,event_type,category=None,details=None):db.add(BrowserApplicationEventRecord(job_id=job_id,event_type=event_type,field_category=category,details_json=details or {}))
