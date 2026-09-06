from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import AgentRunRecord
from app.models.career_intelligence import CareerIntelligenceRun
from app.services.career_intelligence_service import CareerIntelligenceService


router=APIRouter(prefix="/career-intelligence",tags=["career intelligence"])


@router.post("/find-jobs",response_model=CareerIntelligenceRun,status_code=202)
def find_jobs(db:Session=Depends(get_db)):
    try:run=CareerIntelligenceService().enqueue(db)
    except ValueError as exc:raise HTTPException(409,str(exc)) from exc
    return CareerIntelligenceService.read(run)


@router.get("/runs/latest",response_model=CareerIntelligenceRun|None)
def latest_run(db:Session=Depends(get_db)):
    run=db.scalar(select(AgentRunRecord).where(AgentRunRecord.agent_type=="career_intelligence").order_by(AgentRunRecord.id.desc()))
    return CareerIntelligenceService.read(run) if run else None


@router.get("/runs/{run_id}",response_model=CareerIntelligenceRun)
def get_run(run_id:int,db:Session=Depends(get_db)):
    run=db.get(AgentRunRecord,run_id)
    if not run or run.agent_type!="career_intelligence":raise HTTPException(404,"Career-intelligence run not found")
    return CareerIntelligenceService.read(run)
