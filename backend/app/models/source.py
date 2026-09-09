from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ATSType(StrEnum):
    greenhouse="greenhouse"; lever="lever"; ashby="ashby"; smartrecruiters="smartrecruiters"; workday="workday"; workable="workable"; bamboohr="bamboohr"; teamtailor="teamtailor"; recruitee="recruitee"; generic_company_site="generic_company_site"; manual_url="manual_url"; linkedin_reference="linkedin_reference"; icims="icims"; jobvite="jobvite"; successfactors="successfactors"; search_discovery="search_discovery"; email_alert="email_alert"; custom="custom"


class JobSourceBase(BaseModel):
    company: str
    ats_type: ATSType
    board_identifier: str
    careers_url: HttpUrl | None = None
    enabled: bool = True
    scan_frequency: str = "manual"
    company_id: int | None = None
    priority: str = "NORMAL"
    configuration: dict = Field(default_factory=dict)


class JobSourceCreate(JobSourceBase): pass
class JobSourceUpdate(BaseModel):
    company: str | None=None; ats_type: ATSType | None=None; board_identifier: str | None=None; careers_url: HttpUrl | None=None; enabled: bool | None=None; scan_frequency: str | None=None; company_id:int|None=None; priority:str|None=None; configuration:dict|None=None
class SourceEnabledUpdate(BaseModel): enabled: bool


class JobSourceRead(JobSourceBase):
    id:int; last_scanned_at:datetime|None=None; last_success_at:datetime|None=None; last_error:str|None=None; jobs_discovered_total:int=0; created_at:datetime; updated_at:datetime
    last_attempt_at:datetime|None=None;last_failure_at:datetime|None=None;failure_type:str|None=None;consecutive_failures:int=0;average_latency_ms:float|None=None;last_job_count:int=0;retry_after:datetime|None=None;health_status:str="UNKNOWN";disabled_reason:str|None=None
    model_config=ConfigDict(from_attributes=True)
