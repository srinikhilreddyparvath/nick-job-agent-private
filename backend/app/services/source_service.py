from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import JobSourceRecord
from app.models.source import JobSourceCreate,JobSourceUpdate

class SourceService:
    def list(self,db:Session): return db.scalars(select(JobSourceRecord).order_by(JobSourceRecord.company)).all()
    def get(self,db:Session,source_id:int): return db.get(JobSourceRecord,source_id)
    def create(self,db:Session,data:JobSourceCreate):
        record=JobSourceRecord(**data.model_dump(mode="json")); record.careers_url=str(data.careers_url) if data.careers_url else None; db.add(record); db.commit(); db.refresh(record); return record
    def update(self,db:Session,record:JobSourceRecord,data:JobSourceUpdate):
        values=data.model_dump(exclude_unset=True,mode="json");
        for key,value in values.items(): setattr(record,key,value)
        db.commit(); db.refresh(record); return record
    def delete(self,db:Session,record:JobSourceRecord): db.delete(record); db.commit()

