from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import JobSourceRecord
from app.models.scan import ScanRunRead
from app.models.source import JobSourceCreate,JobSourceRead,JobSourceUpdate,SourceEnabledUpdate
from app.services.scan_orchestrator import ScanOrchestrator
from app.services.source_service import SourceService
from app.models.detection import AtsDetectionRequest,AtsDetectionResult
from app.services.ats_detector import AtsDetector

router=APIRouter(prefix="/sources",tags=["sources"]); service=SourceService()
def require(db,source_id):
    record=service.get(db,source_id)
    if not record: raise HTTPException(404,"Source not found")
    return record
@router.get("",response_model=list[JobSourceRead])
def list_sources(db:Session=Depends(get_db)): return service.list(db)
@router.get("/{source_id}",response_model=JobSourceRead)
def get_source(source_id:int,db:Session=Depends(get_db)): return require(db,source_id)
@router.post("",response_model=JobSourceRead,status_code=201)
def create_source(data:JobSourceCreate,db:Session=Depends(get_db)): return service.create(db,data)
@router.put("/{source_id}",response_model=JobSourceRead)
def update_source(source_id:int,data:JobSourceUpdate,db:Session=Depends(get_db)): return service.update(db,require(db,source_id),data)
@router.delete("/{source_id}",status_code=204)
def delete_source(source_id:int,db:Session=Depends(get_db)): service.delete(db,require(db,source_id)); return Response(status_code=204)
@router.patch("/{source_id}/enabled",response_model=JobSourceRead)
def set_enabled(source_id:int,data:SourceEnabledUpdate,db:Session=Depends(get_db)): return service.update(db,require(db,source_id),JobSourceUpdate(enabled=data.enabled))
@router.post("/{source_id}/scan",response_model=ScanRunRead)
def scan_source(source_id:int,db:Session=Depends(get_db)): return ScanOrchestrator().scan(db,[require(db,source_id)])
@router.post("/scan-all",response_model=ScanRunRead)
def scan_all(db:Session=Depends(get_db)):
    sources=db.scalars(select(JobSourceRecord).where(JobSourceRecord.enabled.is_(True))).all(); return ScanOrchestrator().scan(db,sources)
@router.post("/detect",response_model=AtsDetectionResult)
def detect_source(data:AtsDetectionRequest):return AtsDetector().detect(data.company,str(data.careers_url))
@router.post("/detect-and-create",response_model=JobSourceRead,status_code=201)
def detect_and_create(data:AtsDetectionRequest,db:Session=Depends(get_db)):
    result=AtsDetector().detect(data.company,str(data.careers_url));config=result.recommended_source_configuration
    return service.create(db,JobSourceCreate(**config))
