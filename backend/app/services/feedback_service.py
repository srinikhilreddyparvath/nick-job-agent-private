from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import JobFeedbackRecord
from app.models.feedback import JobFeedbackWrite

class FeedbackService:
    def get(self,db:Session,job_id:int): return db.scalar(select(JobFeedbackRecord).where(JobFeedbackRecord.job_id==job_id))
    def upsert(self,db:Session,job_id:int,data:JobFeedbackWrite):
        record=self.get(db,job_id)
        if record:
            record.human_label=data.human_label; record.human_notes=data.human_notes; record.human_role_family=data.human_role_family
        else: record=JobFeedbackRecord(job_id=job_id,human_label=data.human_label,human_notes=data.human_notes,human_role_family=data.human_role_family); db.add(record)
        db.commit(); db.refresh(record); return record
