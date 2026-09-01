from datetime import datetime,timezone
from sqlalchemy.orm import Session
from app.db.models import AgentRunRecord

class AgentRunService:
    def start(self,db:Session,agent_type:str,objective:str,job_id:int|None=None,input_state:dict|None=None,**metadata):
        record=AgentRunRecord(agent_type=agent_type,objective=objective,job_id=job_id,status="running",started_at=datetime.now(timezone.utc),input_state_json=input_state or {},**metadata); db.add(record); db.commit(); db.refresh(record); return record
    def complete(self,db:Session,record:AgentRunRecord,output:dict,actions:list[dict]|None=None,**metadata):
        record.status="completed"; record.completed_at=datetime.now(timezone.utc); record.output_state_json=output; record.actions_json=actions or []
        for key,value in metadata.items():setattr(record,key,value)
        db.commit(); db.refresh(record); return record
    def fail(self,db:Session,record:AgentRunRecord,error:str):
        record.status="failed"; record.completed_at=datetime.now(timezone.utc); record.errors_json=[{"error":error}]; db.commit(); return record
