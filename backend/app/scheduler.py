import os,socket,time
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.core.config import get_settings
from app.db.database import SessionLocal,init_db
from app.db.models import JobSourceRecord,MorningReportRecord,ScanRunRecord
from app.services.morning_report_service import MorningReportService
from app.services.runtime_service import RuntimeControlService
from app.services.scan_orchestrator import ScanOrchestrator
from app.services.autonomy_pipeline import AutonomyPipelineService
from app.services.career_intelligence_service import CareerIntelligenceService
class Scheduler:
 def __init__(self,instance_id=None):self.instance_id=instance_id or f"{socket.gethostname()}-{os.getpid()}";self.runtime=RuntimeControlService();self.last_discovery=None;self.last_queue=None
 def tick(self,db,now=None):
  settings=get_settings();now=now or datetime.now(timezone.utc);self.runtime.heartbeat(db,"scheduler",self.instance_id)
  actions=[]
  if self.last_discovery is None:
   latest_scan=db.scalar(select(ScanRunRecord).where(ScanRunRecord.status.in_(["completed","completed_with_errors"])).order_by(ScanRunRecord.completed_at.desc()).limit(1))
   if latest_scan and latest_scan.completed_at:
    self.last_discovery=latest_scan.completed_at if latest_scan.completed_at.tzinfo else latest_scan.completed_at.replace(tzinfo=timezone.utc)
  if not self.last_discovery or (now-self.last_discovery).total_seconds()>=settings.discovery_interval_minutes*60:
   sources=db.scalars(select(JobSourceRecord).where(JobSourceRecord.enabled.is_(True))).all()
   if sources:
    scan=ScanOrchestrator().scan(db,sources);actions.append("DISCOVERY")
    CareerIntelligenceService(settings=settings).enqueue(db,trigger="scheduled",scan_required=False,scan_id=scan.id);actions.append("CAREER_INTELLIGENCE_QUEUED")
    if settings.application_mode=="auto_submit" and settings.auto_submit_enabled:AutonomyPipelineService().run(db);actions.append("AUTONOMY_PIPELINE")
   self.last_discovery=now
  local=now.astimezone(ZoneInfo(settings.timezone));latest=db.scalar(select(MorningReportRecord).order_by(MorningReportRecord.created_at.desc()).limit(1))
  if local.hour>=settings.morning_report_hour_local and (not latest or latest.created_at.date()<now.date()):MorningReportService().generate(db);actions.append("MORNING_REPORT")
  self.runtime.heartbeat(db,"scheduler",self.instance_id,success=True,details={"actions":actions});return actions
def main():
 settings=get_settings()
 if settings.environment!="production":init_db()
 scheduler=Scheduler()
 while True:
  with SessionLocal() as db:scheduler.tick(db)
  time.sleep(min(settings.queue_interval_minutes*60,60))
if __name__=="__main__":main()
