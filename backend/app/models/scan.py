from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field


class ScanStatus(StrEnum): queued="queued"; running="running"; completed="completed"; completed_with_errors="completed_with_errors"; failed="failed"


class ScanRunRead(BaseModel):
    id:int; started_at:datetime; completed_at:datetime|None=None; status:ScanStatus
    source_count:int=0; successful_source_count:int=0; failed_source_count:int=0
    jobs_fetched:int=0; jobs_filtered:int=0; jobs_deduplicated:int=0; jobs_added:int=0; jobs_updated:int=0; jobs_scored:int=0
    exceptional_count:int=0; strong_count:int=0; possible_count:int=0; weak_count:int=0; skip_count:int=0
    errors_json:list[dict]=Field(default_factory=list); duration_seconds:float|None=None
    jobs_by_source_type:dict[str,int]=Field(default_factory=dict); jobs_by_role_family:dict[str,int]=Field(default_factory=dict); duplicates_across_sources:int=0; source_detection_failures:int=0
    model_config=ConfigDict(from_attributes=True)
