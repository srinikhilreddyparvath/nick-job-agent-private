from sqlalchemy import func,select
from sqlalchemy.orm import Session
from app.db.models import CompanyRecord,JobSourceRecord
from app.models.company import CompanyCreate,CompanyUpdate
from app.services.normalization_service import normalize_company
class CompanyService:
 def list(self,db): return db.scalars(select(CompanyRecord).order_by(CompanyRecord.priority,CompanyRecord.name)).all()
 def get(self,db,id): return db.get(CompanyRecord,id)
 def create(self,db:Session,data:CompanyCreate):
    canonical=normalize_company(data.name); existing=db.scalar(select(CompanyRecord).where(CompanyRecord.canonical_name==canonical))
    if existing:return existing
    values=data.model_dump(mode="json"); values["website_url"]=str(data.website_url) if data.website_url else None; values["careers_url"]=str(data.careers_url) if data.careers_url else None; record=CompanyRecord(**values,canonical_name=canonical); db.add(record);db.commit();db.refresh(record);return record
 def update(self,db,record,data:CompanyUpdate):
    for key,value in data.model_dump(exclude_unset=True,mode="json").items():setattr(record,key,value)
    if data.name:record.canonical_name=normalize_company(data.name)
    db.commit();db.refresh(record);return record
 def delete(self,db,record):db.delete(record);db.commit()
 def read_dict(self,db,record):
    sources=db.scalars(select(JobSourceRecord).where(JobSourceRecord.company_id==record.id)).all(); return {"id":record.id,"name":record.name,"canonical_name":record.canonical_name,"website_url":record.website_url,"careers_url":record.careers_url,"company_type":record.company_type,"priority":record.priority,"enabled":record.enabled,"notes":record.notes,"detected_ats":record.detected_ats,"created_at":record.created_at,"updated_at":record.updated_at,"source_count":len(sources),"last_scan":max((x.last_scanned_at for x in sources if x.last_scanned_at),default=None)}
