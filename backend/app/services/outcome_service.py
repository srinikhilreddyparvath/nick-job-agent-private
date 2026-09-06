from datetime import datetime,timezone
from sqlalchemy import func,select
from app.db.models import ApplicationOutcomeRecord,ApplicationReceiptRecord,JobRecord,JobScoreRecord
VALID={"SUBMITTED","RECRUITER_CONTACT","SCREEN","INTERVIEW","ONSITE","OFFER","REJECTED","WITHDRAWN","NO_RESPONSE","UNKNOWN"}
class OutcomeService:
 def record(self,db,job_id,status,notes=None):
  if status not in VALID:raise ValueError("Invalid outcome")
  job=db.get(JobRecord,job_id);receipt=db.scalar(select(ApplicationReceiptRecord).where(ApplicationReceiptRecord.job_id==job_id));score=db.scalar(select(JobScoreRecord).where(JobScoreRecord.job_id==job_id).order_by(JobScoreRecord.created_at.desc()))
  row=ApplicationOutcomeRecord(job_id=job_id,application_receipt_id=receipt.id if receipt else None,status=status,notes=notes,fit_score=score.overall_score if score else None,role_family=job.role_family,resume_version=receipt.application_package_version if receipt else None,submitted_at=receipt.submitted_at if receipt else None);db.add(row);db.commit();db.refresh(row);return row
 def metrics(self,db):
  total=db.scalar(select(func.count()).select_from(ApplicationOutcomeRecord).where(ApplicationOutcomeRecord.status!="UNKNOWN")) or 0
  if total<5:return {"status":"insufficient_data","labeled_outcomes":total}
  count=lambda statuses:db.scalar(select(func.count()).select_from(ApplicationOutcomeRecord).where(ApplicationOutcomeRecord.status.in_(statuses))) or 0
  return {"status":"available","submitted":total,"response_rate":count(["RECRUITER_CONTACT","SCREEN","INTERVIEW","ONSITE","OFFER"])/total,"screen_rate":count(["SCREEN","INTERVIEW","ONSITE","OFFER"])/total,"interview_rate":count(["INTERVIEW","ONSITE","OFFER"])/total,"offer_rate":count(["OFFER"])/total}
