from datetime import datetime,timedelta,timezone
from sqlalchemy import func,select
from app.db.models import AgentRunRecord,ApplicationQueueItemRecord,ApplicationReceiptRecord,BrowserApplicationEventRecord,JobRecord,MorningReportRecord
class MorningReportService:
 def generate(self,db,since=None):
  end=datetime.now(timezone.utc);start=since or end-timedelta(hours=24)
  count=lambda model,field:db.scalar(select(func.count()).select_from(model).where(field>=start)) or 0
  event=lambda name:db.scalar(select(func.count()).select_from(BrowserApplicationEventRecord).where(BrowserApplicationEventRecord.created_at>=start,BrowserApplicationEventRecord.event_type==name)) or 0
  metrics={"jobs_discovered":count(JobRecord,JobRecord.discovered_at),"semantic_analyses":db.scalar(select(func.count()).select_from(AgentRunRecord).where(AgentRunRecord.started_at>=start,AgentRunRecord.agent_type=="fit")) or 0,"packages_generated":db.scalar(select(func.count()).select_from(AgentRunRecord).where(AgentRunRecord.started_at>=start,AgentRunRecord.agent_type=="application")) or 0,"applications_queued":count(ApplicationQueueItemRecord,ApplicationQueueItemRecord.created_at),"applications_submitted":count(ApplicationReceiptRecord,ApplicationReceiptRecord.submitted_at),"applications_blocked":db.scalar(select(func.count()).select_from(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.status=="BLOCKED")) or 0,"applications_needing_review":db.scalar(select(func.count()).select_from(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.status=="NEEDS_REVIEW")) or 0,"applications_failed":db.scalar(select(func.count()).select_from(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.status=="FAILED")) or 0,"captchas":event("CAPTCHA_DETECTED"),"duplicate_prevented":event("DUPLICATE_PREVENTED"),"estimated_openai_cost":float(db.scalar(select(func.coalesce(func.sum(AgentRunRecord.estimated_cost),0)).where(AgentRunRecord.started_at>=start)) or 0)};row=MorningReportRecord(period_start=start,period_end=end,metrics_json=metrics);db.add(row);db.commit();db.refresh(row);return row
class MorningReportDeliveryProvider:
 def deliver(self,report):raise NotImplementedError
