from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import ScanRunRecord
from app.models.scan import ScanRunRead
router=APIRouter(prefix="/scans",tags=["scans"])
@router.get("",response_model=list[ScanRunRead])
def list_scans(db:Session=Depends(get_db)): return db.scalars(select(ScanRunRecord).order_by(ScanRunRecord.started_at.desc()).limit(100)).all()
@router.get("/{scan_id}",response_model=ScanRunRead)
def get_scan(scan_id:int,db:Session=Depends(get_db)):
    result=db.get(ScanRunRecord,scan_id)
    if not result: raise HTTPException(404,"Scan not found")
    return result
