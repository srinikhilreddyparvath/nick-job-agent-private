from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.models.company import CompanyCreate,CompanyRead,CompanyUpdate
from app.models.detection import AtsDetectionResult
from app.models.source import JobSourceCreate
from app.services.ats_detector import AtsDetector
from app.services.company_service import CompanyService
from app.services.source_service import SourceService
router=APIRouter(prefix="/companies",tags=["companies"]); service=CompanyService()
def require(db,id):
 r=service.get(db,id)
 if not r:raise HTTPException(404,"Company not found")
 return r
@router.get("",response_model=list[CompanyRead])
def companies(db:Session=Depends(get_db)):return [service.read_dict(db,x) for x in service.list(db)]
@router.post("",response_model=CompanyRead,status_code=201)
def create(data:CompanyCreate,db:Session=Depends(get_db)):
 r=service.create(db,data);return service.read_dict(db,r)
@router.put("/{company_id}",response_model=CompanyRead)
def update(company_id:int,data:CompanyUpdate,db:Session=Depends(get_db)):return service.read_dict(db,service.update(db,require(db,company_id),data))
@router.delete("/{company_id}",status_code=204)
def delete(company_id:int,db:Session=Depends(get_db)):service.delete(db,require(db,company_id));return Response(status_code=204)
@router.post("/{company_id}/detect",response_model=AtsDetectionResult)
def detect(company_id:int,db:Session=Depends(get_db)):
 r=require(db,company_id)
 if not r.careers_url:raise HTTPException(400,"Company has no careers URL")
 result=AtsDetector().detect(r.name,r.careers_url);r.detected_ats=result.detected_ats;db.commit();return result
