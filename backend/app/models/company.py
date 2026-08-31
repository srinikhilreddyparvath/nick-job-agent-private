from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel,ConfigDict,HttpUrl
class CompanyType(StrEnum): AI_STARTUP="AI_STARTUP"; TECH_STARTUP="TECH_STARTUP"; RESEARCH_LAB="RESEARCH_LAB"; LARGE_TECH="LARGE_TECH"; MID_SIZE_TECH="MID_SIZE_TECH"; OTHER="OTHER"
class SourcePriority(StrEnum): HIGH="HIGH"; NORMAL="NORMAL"; LOW="LOW"
class CompanyBase(BaseModel):
    name:str; website_url:HttpUrl|None=None; careers_url:HttpUrl|None=None; company_type:CompanyType=CompanyType.OTHER; priority:SourcePriority=SourcePriority.NORMAL; enabled:bool=True; notes:str|None=None
class CompanyCreate(CompanyBase): pass
class CompanyUpdate(BaseModel):
    name:str|None=None; website_url:HttpUrl|None=None; careers_url:HttpUrl|None=None; company_type:CompanyType|None=None; priority:SourcePriority|None=None; enabled:bool|None=None; notes:str|None=None; detected_ats:str|None=None
class CompanyRead(CompanyBase):
    id:int; canonical_name:str; detected_ats:str|None=None; created_at:datetime; updated_at:datetime; source_count:int=0; last_scan:datetime|None=None
    model_config=ConfigDict(from_attributes=True)
