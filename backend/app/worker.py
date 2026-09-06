import os,socket,time
from app.core.config import get_settings
from app.db.database import SessionLocal,init_db
from app.db.models import JobRecord
from app.models.browser import BrowserRunRequest
from app.services.application_queue_service import ApplicationQueueService
from app.services.browser_orchestrator import BrowserOrchestrator
from app.services.runtime_service import QueueLeaseService,RuntimeControlService
from app.services.submission_state_service import SubmissionStateService
from app.services.career_intelligence_service import CareerIntelligenceService

class ApplicationWorker:
 def __init__(self,worker_id=None):self.worker_id=worker_id or f"{socket.gethostname()}-{os.getpid()}";self.leases=QueueLeaseService();self.runtime=RuntimeControlService()
 def run_once(self,db):
  settings=get_settings();self.leases.recover(db);self.runtime.heartbeat(db,"worker",self.worker_id)
  intelligence=CareerIntelligenceService(settings=settings).process_next(db)
  if intelligence:return {"status":intelligence.status,"career_intelligence_run_id":intelligence.id}
  if settings.application_mode=="manual":return {"status":"IDLE_MANUAL_MODE"}
  if settings.application_mode=="auto_submit":
   allowed,reason=self.runtime.auto_submit_allowed(db)
   if not allowed:return {"status":"PAUSED","reason":reason}
  item=self.leases.claim(db,self.worker_id)
  if not item:return {"status":"IDLE"}
  try:
   if self.runtime.paused(db):self.leases.release(db,item,"QUEUED","AUTONOMY_PAUSED");return {"status":"PAUSED"}
   queue_service=ApplicationQueueService()
   if settings.application_mode=="auto_submit":
    job=db.get(JobRecord,item.job_id)
    submission_lock=SubmissionStateService().lockout_reason(db,item.job_id)
    if submission_lock:
     self.leases.release(db,item,"NEEDS_REVIEW" if submission_lock=="SUBMISSION_UNVERIFIED" else "BLOCKED",submission_lock);return {"job_id":item.job_id,"status":"NEEDS_REVIEW" if submission_lock=="SUBMISSION_UNVERIFIED" else "BLOCKED"}
    if not job or not queue_service.can_submit(db,job):
     self.leases.release(db,item,"RETRYABLE","AUTO_APPLY_POLICY_CAP_OR_THROTTLE");return {"job_id":item.job_id,"status":"RETRYABLE"}
   mode="AUTO_SUBMIT" if settings.application_mode=="auto_submit" else "FILL_ONLY";result=BrowserOrchestrator().run(db,item.job_id,BrowserRunRequest(mode=mode,dry_run=False))
   status="SUBMITTED" if result.submitted else "NEEDS_REVIEW" if result.status=="SUBMISSION_UNVERIFIED" or result.fields_needing_review or result.blockers else "READY"
   self.leases.release(db,item,status,",".join(result.blockers) or None);self.runtime.heartbeat(db,"worker",self.worker_id,success=True,details={"last_job_id":item.job_id,"last_status":status});return {"job_id":item.job_id,"status":status}
  except Exception as exc:self.leases.release(db,item,"RETRYABLE",type(exc).__name__);return {"job_id":item.job_id,"status":"RETRYABLE"}
def main():
 settings=get_settings()
 if settings.environment!="production":init_db()
 worker=ApplicationWorker()
 while True:
  with SessionLocal() as db:worker.run_once(db)
  time.sleep(settings.worker_poll_seconds)
if __name__=="__main__":main()
