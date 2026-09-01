from datetime import datetime
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, ConfigDict

class HumanLabel(StrEnum): excellent="excellent"; good="good"; maybe="maybe"; poor="poor"
class JobFeedbackWrite(BaseModel): human_label:HumanLabel; human_notes:str|None=None; human_role_family:str|None=None
class JobFeedbackRead(JobFeedbackWrite):
    id:int; job_id:int; labeled_at:datetime; updated_at:datetime
    model_config=ConfigDict(from_attributes=True)

class EvaluationState(StrEnum): ready="ready"; insufficient_data="insufficient_data"
class RankingEvaluation(BaseModel):
    state:EvaluationState; labeled_jobs:int; minimum_required:int; metrics:dict[str,Any]|None=None; message:str
