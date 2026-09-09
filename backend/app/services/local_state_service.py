import shutil
from pathlib import Path
from sqlalchemy import func,select

from app.core.config import Settings,get_settings
from app.db.database import Base
from app.db.models import ApplicationRecord
from app.services.candidate_extraction_service import private_storage_path
from app.services.candidate_persistence_service import configured_output_path


class LocalStateService:
    """Deletes the single user's generated state while preserving code, examples, and secrets."""
    CONFIRMATION="RESET ROLECALL"
    def __init__(self,settings:Settings|None=None):self.settings=settings or get_settings()
    def reset(self,db,confirmation:str)->dict:
        if confirmation!=self.CONFIRMATION:raise ValueError(f'Type "{self.CONFIRMATION}" to confirm')
        protected=db.scalar(select(func.count()).select_from(ApplicationRecord).where(ApplicationRecord.status.in_(["SUBMITTED","SUBMISSION_UNVERIFIED"])).execution_options(candidate_history_audit=True)) or 0
        if protected:raise ValueError("Reset is blocked because durable submitted or submission-unverified safety records exist. Reconcile or archive them through a dedicated safe workflow; reset will not erase retry protection.")
        for table in reversed(Base.metadata.sorted_tables):db.execute(table.delete())
        db.commit()
        removed=[]
        for value in (self.settings.candidate_profile_path,self.settings.candidate_evidence_path,self.settings.candidate_preferences_path,self.settings.candidate_answer_bank_path,self.settings.candidate_application_policy_path):
            path=configured_output_path(value)
            if path.exists():path.unlink();removed.append(path.name)
        from app.services.candidate_context_service import state_path
        for path in (state_path(self.settings), state_path(self.settings).with_suffix(".pending.json")):
            if path.exists(): path.unlink(); removed.append(path.name)
        private=private_storage_path(self.settings)
        if private.exists():shutil.rmtree(private)
        private.mkdir(parents=True,exist_ok=True)
        artifacts=Path(self.settings.artifact_storage_path)
        if not artifacts.is_absolute():artifacts=(Path(__file__).resolve().parents[2]/artifacts).resolve()
        if artifacts.exists() and artifacts.is_dir():
            for child in artifacts.iterdir():
                if child.is_dir():shutil.rmtree(child)
                else:child.unlink()
        return {"status":"RESET","candidate_files_removed":len(removed),"database_tables_cleared":len(Base.metadata.sorted_tables)}
