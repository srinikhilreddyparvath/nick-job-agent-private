from pydantic import BaseModel,Field,HttpUrl
class AtsDetectionRequest(BaseModel): company:str; careers_url:HttpUrl
class AtsDetectionResult(BaseModel):
    detected_ats:str; confidence:float=Field(ge=0,le=1); board_identifier:str|None=None; detected_urls:list[str]=Field(default_factory=list); reasons:list[str]=Field(default_factory=list); recommended_source_configuration:dict
