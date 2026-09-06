from datetime import datetime,timedelta,timezone
from pydantic import BaseModel
from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import AgentRunRecord,ApplicationOutcomeRecord,JobExclusionRecord,MorningReportRecord,RuntimeHeartbeatRecord,ScanRunRecord
from app.core.config import get_settings
from sqlalchemy import func
from app.services.morning_report_service import MorningReportService
from app.services.outcome_service import OutcomeService
from app.services.runtime_service import RuntimeControlService
from app.services.local_state_service import LocalStateService
router=APIRouter(tags=["operations"])
class SettingValue(BaseModel):value:bool
class OutcomeInput(BaseModel):status:str;notes:str|None=None
class ExclusionInput(BaseModel):reason:str|None=None
class ResetInput(BaseModel):confirmation:str
@router.get("/operations/status")
def status(db:Session=Depends(get_db)):
 beats=db.scalars(select(RuntimeHeartbeatRecord)).all();now=datetime.now(timezone.utc)
 last_scan=db.scalar(select(ScanRunRecord).where(ScanRunRecord.status.in_(["completed","completed_with_errors"])).order_by(ScanRunRecord.completed_at.desc()).limit(1));cfg=get_settings()
 return {"api":"ONLINE","database":"ONLINE","autonomy_paused":RuntimeControlService().paused(db),"playwright_available":True,"openai_configured":bool(cfg.openai_api_key),"last_successful_discovery":last_scan.completed_at if last_scan else None,"heartbeats":{x.component:{"status":"ONLINE" if (now-(x.last_heartbeat_at.replace(tzinfo=timezone.utc) if x.last_heartbeat_at.tzinfo is None else x.last_heartbeat_at)).total_seconds()<180 else "OFFLINE","last_heartbeat_at":x.last_heartbeat_at,"last_success_at":x.last_success_at} for x in beats}}
@router.post("/operations/pause")
def pause(body:SettingValue,db:Session=Depends(get_db)):RuntimeControlService().set(db,"AUTO_APPLY_PAUSED",body.value);return {"autonomy_paused":body.value}
@router.get("/reports/morning/latest")
def latest_report(db:Session=Depends(get_db)):
 row=db.scalar(select(MorningReportRecord).order_by(MorningReportRecord.created_at.desc()).limit(1)) or MorningReportService().generate(db);return {"period_start":row.period_start,"period_end":row.period_end,**row.metrics_json}
@router.post("/jobs/{job_id}/outcome")
def outcome(job_id:int,body:OutcomeInput,db:Session=Depends(get_db)):
 try:return OutcomeService().record(db,job_id,body.status,body.notes)
 except ValueError as exc:raise HTTPException(422,str(exc))
@router.get("/outcomes")
def outcomes(db:Session=Depends(get_db)):return db.scalars(select(ApplicationOutcomeRecord).order_by(ApplicationOutcomeRecord.updated_at.desc())).all()
@router.get("/outcomes/metrics")
def outcome_metrics(db:Session=Depends(get_db)):return OutcomeService().metrics(db)
@router.get("/operations/costs")
def costs(db:Session=Depends(get_db)):
 now=datetime.now(timezone.utc);day=now.replace(hour=0,minute=0,second=0,microsecond=0);week=day-timedelta(days=day.weekday());month=day.replace(day=1)
 total=lambda start:float(db.scalar(select(func.coalesce(func.sum(AgentRunRecord.estimated_cost),0)).where(AgentRunRecord.started_at>=start)) or 0)
 calls=lambda start:db.scalar(select(func.count()).select_from(AgentRunRecord).where(AgentRunRecord.started_at>=start)) or 0
 return {"today":total(day),"week":total(week),"month":total(month),"generation_calls_today":calls(day)}
@router.post("/operations/reset-local-state")
def reset_local_state(body:ResetInput,db:Session=Depends(get_db)):
 try:return LocalStateService().reset(db,body.confirmation)
 except ValueError as exc:raise HTTPException(422,str(exc)) from exc
@router.post("/jobs/{job_id}/never-apply")
def never_apply(job_id:int,body:ExclusionInput,db:Session=Depends(get_db)):
 row=db.get(JobExclusionRecord,job_id) or JobExclusionRecord(job_id=job_id,reason=body.reason);row.reason=body.reason;db.add(row);db.commit();return {"job_id":job_id,"never_apply":True}
@router.delete("/jobs/{job_id}/never-apply")
def allow_apply(job_id:int,db:Session=Depends(get_db)):
 row=db.get(JobExclusionRecord,job_id)
 if row:db.delete(row);db.commit()
 return {"job_id":job_id,"never_apply":False}
