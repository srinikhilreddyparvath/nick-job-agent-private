from datetime import datetime,timedelta,timezone
from uuid import uuid4
from sqlalchemy import or_,select
from app.core.config import get_settings
from app.db.models import ApplicationQueueItemRecord,ApplicationReceiptRecord,RuntimeHeartbeatRecord,RuntimeSettingRecord

class RuntimeControlService:
 def get(self,db,key,default=None):
  row=db.get(RuntimeSettingRecord,key);return row.value_json if row else default
 def set(self,db,key,value):
  row=db.get(RuntimeSettingRecord,key) or RuntimeSettingRecord(key=key,value_json=value);row.value_json=value;db.add(row);db.commit();return value
 def paused(self,db):return bool(self.get(db,"AUTO_APPLY_PAUSED",get_settings().auto_apply_paused))
 def auto_submit_allowed(self,db,explicit_override=False):
  s=get_settings()
  if self.paused(db) or not s.auto_submit_enabled or s.application_mode!="auto_submit":return False,"AUTO_SUBMIT_DISABLED_OR_PAUSED"
  if explicit_override or s.auto_submit_allow_without_receipt:return True,None
  receipt=db.scalar(select(ApplicationReceiptRecord.id).limit(1));return (bool(receipt),None if receipt else "FIRST_VERIFIED_RECEIPT_REQUIRED")
 def heartbeat(self,db,component,instance_id,status="ONLINE",success=False,details=None):
  now=datetime.now(timezone.utc);row=db.get(RuntimeHeartbeatRecord,component) or RuntimeHeartbeatRecord(component=component,instance_id=instance_id);row.instance_id=instance_id;row.status=status;row.last_heartbeat_at=now;row.details_json=details or {};row.last_success_at=now if success else row.last_success_at;db.add(row);db.commit();return row

class QueueLeaseService:
 def claim(self,db,worker_id,lease_seconds=None):
  now=datetime.now(timezone.utc);query=select(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.status.in_(["QUEUED","RETRYABLE"]),or_(ApplicationQueueItemRecord.lease_expires_at.is_(None),ApplicationQueueItemRecord.lease_expires_at<now)).order_by(ApplicationQueueItemRecord.priority.desc()).limit(1)
  if db.bind.dialect.name=="postgresql":query=query.with_for_update(skip_locked=True)
  row=db.scalar(query)
  if not row:return None
  row.lease_owner=worker_id;row.lease_expires_at=now+timedelta(seconds=lease_seconds or get_settings().worker_lease_seconds);row.heartbeat_at=now;row.status="PREPARING";db.commit();db.refresh(row);return row
 def release(self,db,row,status,error=None):row.status=status;row.last_error=error;row.lease_owner=None;row.lease_expires_at=None;row.heartbeat_at=datetime.now(timezone.utc);db.commit()
 def recover(self,db):
  now=datetime.now(timezone.utc);rows=db.scalars(select(ApplicationQueueItemRecord).where(ApplicationQueueItemRecord.lease_expires_at<now)).all();count=0
  for row in rows:
   row.status="NEEDS_REVIEW" if row.submit_started_at else "RETRYABLE";row.block_reason="SUBMISSION_UNVERIFIED" if row.submit_started_at else row.block_reason;row.lease_owner=None;row.lease_expires_at=None;count+=1
  db.commit();return count
