from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

class AgentType(StrEnum): scout="scout"; fit="fit"; research="research"; application="application"; reviewer="reviewer"; browser="browser"; career_intelligence="career_intelligence"
class AgentRunStatus(StrEnum): queued="queued"; running="running"; waiting_for_human="waiting_for_human"; completed="completed"; failed="failed"; cancelled="cancelled"
class AgentDefinition(BaseModel):
    agent_type:AgentType; objective:str; allowed_tools:list[str]; input_state:list[str]; output_state:list[str]; allowed_actions:list[str]; evidence_access:str; failure_behavior:str; requires_human_review_conditions:list[str]; active:bool
class AgentRunRead(BaseModel):
    id:int; agent_type:AgentType; objective:str; job_id:int|None=None; status:AgentRunStatus; started_at:datetime|None=None; completed_at:datetime|None=None; input_state_json:dict[str,Any]=Field(default_factory=dict); output_state_json:dict[str,Any]=Field(default_factory=dict); actions_json:list[dict]=Field(default_factory=list); errors_json:list[dict]=Field(default_factory=list); requires_human_review:bool=False
    provider:str|None=None; model:str|None=None; prompt_version:str|None=None; temperature:float|None=None; evidence_ids_used:list[str]=Field(default_factory=list); sources_used:list[str]=Field(default_factory=list); input_tokens:int=0; output_tokens:int=0; cached_tokens:int=0; estimated_cost:float=0; latency_ms:int=0
    model_config=ConfigDict(from_attributes=True)
