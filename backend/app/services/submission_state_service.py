import hashlib
from pathlib import Path
from sqlalchemy import select

from app.db.models import ApplicationEventRecord,ApplicationPackageRecord,ApplicationReceiptRecord,ApplicationRecord,BrowserApplicationEventRecord,JobRecord


LOCKED_STATES={"SUBMISSION_UNVERIFIED","SUBMITTED"}
CLICK_EVENTS={"SUBMIT_CLICKED"}
CONFIRM_EVENTS={"SUBMISSION_CONFIRMED"}


class SubmissionStateService:
 def application(self,db,job_id):return db.scalar(select(ApplicationRecord).where(ApplicationRecord.job_id==job_id))
 def transition(self,db,job_id,status,note,*,commit=False):
  application=self.application(db,job_id)
  if application is None:raise ValueError("APPLICATION_NOT_FOUND")
  previous=application.status
  if previous!=status:
   application.status=status;db.add(application);db.add(ApplicationEventRecord(application_id=application.id,from_status=previous,to_status=status,note=note))
  if commit:db.commit();db.refresh(application)
  return application
 def evidence(self,db,job_id):
  event_types=set(db.scalars(select(BrowserApplicationEventRecord.event_type).where(BrowserApplicationEventRecord.job_id==job_id)).all())
  receipt=db.scalar(select(ApplicationReceiptRecord).where(ApplicationReceiptRecord.job_id==job_id))
  return event_types,receipt
 def reconcile(self,db,job_id,*,commit=True):
  application=self.application(db,job_id)
  if application is None:raise ValueError("APPLICATION_NOT_FOUND")
  event_types,receipt=self.evidence(db,job_id)
  if receipt or event_types & CONFIRM_EVENTS:
   status="SUBMITTED";note="Submission reconciled from a verified receipt or durable confirmation event."
  elif event_types & CLICK_EVENTS:
   status="SUBMISSION_UNVERIFIED";note="Real external Ashby submit control was clicked, but external confirmation could not be verified. Reconstructed from durable browser submission events."
  else:return application
  application=self.transition(db,job_id,status,note)
  if status=="SUBMITTED" and receipt is None:
   confirmation=db.scalar(select(BrowserApplicationEventRecord).where(BrowserApplicationEventRecord.job_id==job_id,BrowserApplicationEventRecord.event_type=="SUBMISSION_CONFIRMED").order_by(BrowserApplicationEventRecord.id.desc()).limit(1));job=db.get(JobRecord,job_id);package=db.scalar(select(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id==job_id).order_by(ApplicationPackageRecord.id.desc()).limit(1))
   if confirmation is None or job is None or package is None or not package.tailored_resume_path or not Path(package.tailored_resume_path).exists():raise ValueError("VERIFIED_SUBMISSION_RECEIPT_RECONCILIATION_INCOMPLETE")
   inspection=db.scalar(select(BrowserApplicationEventRecord).where(BrowserApplicationEventRecord.job_id==job_id,BrowserApplicationEventRecord.event_type=="FORM_INSPECTED").order_by(BrowserApplicationEventRecord.id.desc()).limit(1));details=confirmation.details_json or {};db.add(ApplicationReceiptRecord(application_id=application.id,job_id=job_id,company=job.company,role=job.title,ats=((inspection.details_json or {}).get("ats") if inspection else None) or "unknown",apply_url=job.apply_url,confirmation_url=details.get("confirmation_url"),external_confirmation_text="; ".join(details.get("signals",[])) or None,resume_artifact_hash=hashlib.sha256(Path(package.tailored_resume_path).read_bytes()).hexdigest(),application_package_version=package.resume_version_id))
  if commit:db.commit();db.refresh(application)
  return application
 def lockout_reason(self,db,job_id):
  application=self.application(db,job_id);event_types,receipt=self.evidence(db,job_id)
  if receipt or (application and application.status=="SUBMITTED"):return "ALREADY_SUBMITTED"
  if (application and application.status=="SUBMISSION_UNVERIFIED") or event_types & CLICK_EVENTS:return "SUBMISSION_UNVERIFIED"
  return None
