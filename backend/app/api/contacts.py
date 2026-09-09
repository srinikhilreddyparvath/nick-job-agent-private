from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.contact import ContactList,OutreachPreview
from app.services.contact_intelligence_service import ContactIntelligenceService

router=APIRouter(prefix="/jobs/{job_id}/contacts",tags=["contact-intelligence"])
service=ContactIntelligenceService()

@router.get("",response_model=ContactList)
def list_contacts(job_id:int,db:Session=Depends(get_db)):return service.list(db,job_id)

@router.post("/discover",response_model=ContactList)
def discover_public_contacts(job_id:int,force:bool=False,db:Session=Depends(get_db)):
    try:return service.discover(db,job_id,force=force)
    except LookupError as exc:raise HTTPException(404,str(exc)) from exc

@router.post("/{contact_id}/outreach-preview",response_model=OutreachPreview)
def preview_outreach(job_id:int,contact_id:int,db:Session=Depends(get_db)):
    try:return service.outreach(db,job_id,contact_id)
    except LookupError as exc:raise HTTPException(404,str(exc)) from exc
