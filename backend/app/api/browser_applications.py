from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import ApplicationFormRecord,ApplicationQueueItemRecord,ApplicationReceiptRecord
from app.services.runtime_service import RuntimeControlService
from app.services.field_mapping_service import FieldMappingService
from app.models.browser import *
from app.services.application_queue_service import ApplicationQueueService
from app.services.browser_orchestrator import BrowserOrchestrator
from app.models.application import ApplicationRead
from app.services.submission_state_service import SubmissionStateService

router=APIRouter(tags=["browser-applications"]);runtime_policy=AutoApplyPolicy()
@router.get("/jobs/{job_id}/application-eligibility",response_model=EligibilityDecision)
def eligibility(job_id:int,manual_override:bool=False,db:Session=Depends(get_db)):
 result=BrowserOrchestrator().decision(db,job_id,manual_override)
 if not result:raise HTTPException(404,"Job not found")
 return result
@router.post("/jobs/{job_id}/apply-anyway",response_model=EligibilityDecision)
def apply_anyway(job_id:int,request:ApplyOverrideRequest,db:Session=Depends(get_db)):
 result=BrowserOrchestrator().decision(db,job_id,request.enabled)
 if not result:raise HTTPException(404,"Job not found")
 return result
@router.post("/jobs/{job_id}/inspect-form",response_model=BrowserRunResult)
def inspect(job_id:int,request:BrowserRunRequest,db:Session=Depends(get_db)):request.mode="INSPECT_ONLY";request.dry_run=True;return BrowserOrchestrator().run(db,job_id,request)
@router.post("/jobs/{job_id}/fill-application",response_model=BrowserRunResult)
def fill(job_id:int,request:BrowserRunRequest,db:Session=Depends(get_db)):request.mode="FILL_ONLY";request.dry_run=True;return BrowserOrchestrator().run(db,job_id,request)
@router.post("/jobs/{job_id}/submit-application",response_model=BrowserRunResult)
def submit(job_id:int,db:Session=Depends(get_db)):return BrowserOrchestrator().run(db,job_id,BrowserRunRequest(mode="USER_TRIGGERED_SUBMIT",dry_run=False))
@router.post("/jobs/{job_id}/reconcile-submission",response_model=ApplicationRead)
def reconcile_submission(job_id:int,db:Session=Depends(get_db)):
 try:return SubmissionStateService().reconcile(db,job_id)
 except ValueError:raise HTTPException(404,"Application not found")
@router.get("/jobs/{job_id}/application-form",response_model=ApplicationFormSchema)
def form(job_id:int,db:Session=Depends(get_db)):
 row=db.scalar(select(ApplicationFormRecord).where(ApplicationFormRecord.job_id==job_id))
 if not row:raise HTTPException(404,"Application form not inspected")
 schema=ApplicationFormSchema.model_validate(row.schema_json)
 required=[field for field in schema.fields if field.required]
 resolved=bool(required) and all(field.write_allowed and not field.requires_human_review for field in required)
 actionable=any(control.actionable and control.visible and control.enabled for control in schema.submit_controls)
 compatible_ready=resolved and actionable and not schema.captcha_detected and not schema.authentication_required
 schema.status=row.status
 if row.status in {"INSPECTED","READY_TO_SUBMIT"}:schema.status="READY_TO_SUBMIT" if compatible_ready else "SUBMIT_CONTROL_NOT_FOUND" if resolved and not actionable else "FORM_NOT_READY"
 return schema
@router.post("/jobs/{job_id}/application-form/resolve")
def resolve_form_field(job_id:int,request:FormResolutionRequest,db:Session=Depends(get_db)):
 normalized=FieldMappingService().normalize(request.field_label);scope=request.scope.upper()
 if scope not in {"JUST_THIS_APPLICATION","SAVE_AS_STANDING_POLICY"}:raise HTTPException(422,"Invalid resolution scope")
 key=f"STANDING_ANSWER:{normalized}" if scope=="SAVE_AS_STANDING_POLICY" else f"FORM_ANSWER:{job_id}:{normalized}";RuntimeControlService().set(db,key,request.answer);return {"job_id":job_id,"field_label":request.field_label,"scope":scope,"saved":True}
@router.post("/application-queue/{job_id}",response_model=QueueItemRead)
def enqueue(job_id:int,manual_override:bool=False,db:Session=Depends(get_db)):
 try:return ApplicationQueueService(runtime_policy).enqueue(db,job_id,manual_override)
 except ValueError as exc:raise HTTPException(409,str(exc))
@router.get("/application-queue",response_model=list[QueueItemRead])
def queue(db:Session=Depends(get_db)):return db.scalars(select(ApplicationQueueItemRecord).order_by(ApplicationQueueItemRecord.priority.desc())).all()
@router.get("/application-receipts",response_model=list[ApplicationReceiptRead])
def receipts(db:Session=Depends(get_db)):return db.scalars(select(ApplicationReceiptRecord).order_by(ApplicationReceiptRecord.submitted_at.desc())).all()
@router.get("/application-summary")
def summary(db:Session=Depends(get_db)):return ApplicationQueueService(runtime_policy).summary(db)
@router.get("/application-settings")
def settings():
 cfg=get_settings();return {"application_mode":cfg.application_mode,"auto_submit_enabled":cfg.auto_submit_enabled,"auto_apply_paused":cfg.auto_apply_paused,"policy":runtime_policy}
@router.patch("/application-settings")
def update_settings(request:AutoApplySettingsUpdate,db:Session=Depends(get_db)):
 cfg=get_settings()
 if request.application_mode is not None:
  if request.application_mode not in {"manual","fill_only","auto_submit"}:raise HTTPException(422,"Invalid application mode")
  cfg.application_mode=request.application_mode
 if request.auto_submit_enabled is not None:
  if request.auto_submit_enabled:
   has_receipt=db.scalar(select(ApplicationReceiptRecord.id).limit(1))
   if not has_receipt and not request.override_receipt_prerequisite and not cfg.auto_submit_allow_without_receipt:raise HTTPException(409,"FIRST_VERIFIED_RECEIPT_REQUIRED")
  cfg.auto_submit_enabled=request.auto_submit_enabled
 if request.auto_apply_paused is not None:RuntimeControlService().set(db,"AUTO_APPLY_PAUSED",request.auto_apply_paused)
 if request.policy is not None:
  global runtime_policy;runtime_policy=request.policy
 return {"application_mode":cfg.application_mode,"auto_submit_enabled":cfg.auto_submit_enabled,"auto_apply_paused":RuntimeControlService().paused(db),"policy":runtime_policy}
