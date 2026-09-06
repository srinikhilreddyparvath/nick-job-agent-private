from datetime import datetime,timezone
from sqlalchemy import func,select
from app.db.models import ApplicationPackageRecord,ApplicationQueueItemRecord,ApplicationReceiptRecord,JobExclusionRecord,JobRecord
from app.core.config import get_settings
from app.services.runtime_service import RuntimeControlService
from app.models.browser import AutoApplyPolicy
from app.services.application_eligibility import ApplicationEligibilityPolicy
from app.services.job_service import JobService
from app.services.submission_state_service import SubmissionStateService

class ApplicationQueueService:
 def __init__(self,policy=None):self.policy=policy or AutoApplyPolicy();self.eligibility=ApplicationEligibilityPolicy()
 def enqueue(self,db,job_id,manual_override=False):
  job=db.get(JobRecord,job_id);package=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id))
  if not job or not package:raise ValueError("Job and package are required")
  blockers=[] if package.status in {"READY_FOR_REVIEW","APPROVED"} else ["PACKAGE_REVIEW_NOT_PASSED"]
  submission_lock=SubmissionStateService().lockout_reason(db,job_id)
  if submission_lock:blockers.append(submission_lock)
  if db.get(JobExclusionRecord,job_id):blockers.append("JOB_NEVER_APPLY")
  if job.company.casefold() in {x.casefold() for x in self.policy.excluded_companies}:blockers.append("COMPANY_EXCLUDED")
  text=f"{job.title} {job.description}".casefold()
  if any(keyword.casefold() in text for keyword in self.policy.excluded_keywords):blockers.append("ROLE_EXCLUDED")
  decision=self.eligibility.evaluate(JobService().to_schema(job),type("P",(),{"status":package.status})(),manual_override=manual_override,hard_blockers=blockers)
  row=db.scalar(select(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.job_id==job_id,ApplicationQueueItemRecord.application_package_id==package.id)) or ApplicationQueueItemRecord(job_id=job_id,application_package_id=package.id)
  row.priority=decision.priority;row.eligibility=decision.eligibility.value;row.status="QUEUED" if decision.eligibility.value.startswith("ELIGIBLE") else "BLOCKED" if decision.eligibility=="BLOCKED" else "NEEDS_REVIEW";row.block_reason=",".join(decision.hard_blockers) or None;db.add(row);db.commit();db.refresh(row);return row
 def can_submit(self,db,job):
  midnight=datetime.combine(datetime.now(timezone.utc).date(),datetime.min.time());total=db.scalar(select(func.count()).select_from(ApplicationReceiptRecord).where(ApplicationReceiptRecord.submitted_at>=midnight)) or 0;company=db.scalar(select(func.count()).select_from(ApplicationReceiptRecord).where(ApplicationReceiptRecord.company==job.company,ApplicationReceiptRecord.submitted_at>=midnight)) or 0
  last=db.scalar(select(ApplicationReceiptRecord).order_by(ApplicationReceiptRecord.submitted_at.desc()).limit(1));spacing=not last or (datetime.now(timezone.utc)-last.submitted_at.replace(tzinfo=timezone.utc) if last.submitted_at.tzinfo is None else datetime.now(timezone.utc)-last.submitted_at).total_seconds()>=get_settings().auto_apply_min_interval_seconds
  return not RuntimeControlService().paused(db) and not db.get(JobExclusionRecord,job.id) and total<self.policy.daily_application_cap and company<self.policy.company_daily_cap and spacing and not SubmissionStateService().lockout_reason(db,job.id)
 def process(self,db,handler,limit=25):
  rows=db.scalars(select(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.status.in_(["QUEUED","RETRYABLE"])).order_by(ApplicationQueueItemRecord.priority.desc()).limit(limit)).all();results=[]
  for row in rows:
   try:row.attempt_count+=1;result=handler(row);row.status=result.get("status","FAILED");row.last_error=result.get("error");results.append(result)
   except Exception as exc:row.status="FAILED";row.last_error=type(exc).__name__;results.append({"job_id":row.job_id,"status":"FAILED"})
   db.commit()
  return results
 def summary(self,db):
  statuses=dict(db.execute(select(ApplicationQueueItemRecord.status,func.count()).group_by(ApplicationQueueItemRecord.status)).all());jobs=db.scalar(select(func.count()).select_from(JobRecord)) or 0;eligible=sum(statuses.get(x,0) for x in ("QUEUED","PREPARING","FILLING","READY","SUBMITTING","SUBMITTED"));packages=db.scalar(select(func.count()).select_from(ApplicationPackageRecord).where(ApplicationPackageRecord.status.in_(["READY_FOR_REVIEW","APPROVED"]))) or 0
  return {"discovered":jobs,"eligible":eligible,"packages_ready":packages,"queued":statuses.get("QUEUED",0),"filled":statuses.get("READY",0),"submitted":statuses.get("SUBMITTED",0),"needs_review":statuses.get("NEEDS_REVIEW",0),"blocked":statuses.get("BLOCKED",0),"failed":statuses.get("FAILED",0),"estimated_llm_cost":float(db.scalar(select(func.coalesce(func.sum(ApplicationPackageRecord.estimated_cost),0))) or 0)}
