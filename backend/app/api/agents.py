from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.agents.application import ApplicationAgent
from app.agents.browser import BrowserAgent
from app.agents.fit import FitAgent
from app.agents.researcher import ResearchAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.scout import ScoutAgent
from app.db.database import get_db
from app.db.models import AgentRunRecord
from app.models.agent import AgentDefinition,AgentRunRead

router=APIRouter(prefix="/agents",tags=["agents"])
AGENTS=[ScoutAgent,FitAgent,ResearchAgent,ApplicationAgent,ReviewerAgent,BrowserAgent]
@router.get("",response_model=list[AgentDefinition])
def definitions(): return [agent.definition for agent in AGENTS]
@router.get("/runs",response_model=list[AgentRunRead])
def runs(db:Session=Depends(get_db)): return db.scalars(select(AgentRunRecord).order_by(AgentRunRecord.id.desc())).all()
@router.get("/runs/{run_id}",response_model=AgentRunRead)
def run(run_id:int,db:Session=Depends(get_db)):
    record=db.get(AgentRunRecord,run_id)
    if not record: raise HTTPException(404,"Agent run not found")
    return record
