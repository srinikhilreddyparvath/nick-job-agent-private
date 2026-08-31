from pydantic import BaseModel,Field,HttpUrl
from app.models.job import Job
class JobUrlIngestRequest(BaseModel): url:HttpUrl
class JobTextIngestRequest(BaseModel): source_url:HttpUrl; job_description_text:str=Field(min_length=20); company:str|None=None; title:str|None=None; location:str|None=None
class JobIngestResult(BaseModel): status:str; job:Job; duplicate:bool=False; message:str
