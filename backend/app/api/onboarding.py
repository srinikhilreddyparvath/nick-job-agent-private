from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.onboarding import OnboardingApprovalRequest, OnboardingState, ResumeIngestionResult
from app.models.profile import JobPreferences
from app.services.candidate_extraction_service import CandidateExtractionService, ResumeExtractionError
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.llm_service import LLMError


router = APIRouter(prefix="/onboarding", tags=["onboarding"])

ERROR_MESSAGES={"AI_REQUEST_TIMED_OUT":"Resume extraction timed out. Try extraction again.","AI_RESPONSE_INCOMPLETE":"The AI response was incomplete. Try extraction again.","RESUME_STRUCTURE_INVALID":"The extracted profile could not be validated. Try extraction again.","AI_PROVIDER_REJECTED":"The AI provider temporarily rejected the request. Try again later.","AI_RESPONSE_REFUSED":"The AI provider could not process this resume. Review the document and try again.","AI_PROVIDER_UNAVAILABLE":"The AI provider is temporarily unavailable. Try again later."}

def extraction_detail(exc:LLMError,prefix:str)->dict:
    code=getattr(exc,"safe_category","AI_EXTRACTION_FAILED")
    return {"code":code,"message":f"{prefix} {ERROR_MESSAGES.get(code,'AI extraction failed unexpectedly. Try again later.')}"}


@router.get("", response_model=OnboardingState)
def get_onboarding_state(): return CandidatePersistenceService().state()


@router.post("/resume", response_model=ResumeIngestionResult)
def ingest_resume(file: UploadFile = File(...), use_mock: bool = Form(False)):
    try: return CandidateExtractionService().ingest(file, use_mock=use_mock)
    except ResumeExtractionError as exc: raise HTTPException(422, str(exc)) from exc
    except LLMError as exc: raise HTTPException(503,extraction_detail(exc,"Your resume was saved, but")) from exc


@router.post("/resume/retry",response_model=ResumeIngestionResult)
def retry_resume_extraction(use_mock:bool=False):
    try:return CandidateExtractionService().retry_latest(use_mock=use_mock)
    except ResumeExtractionError as exc:raise HTTPException(422,str(exc)) from exc
    except LLMError as exc:raise HTTPException(503,extraction_detail(exc,"Your resume remains saved, but")) from exc


@router.put("/approve", response_model=OnboardingState)
def approve_onboarding(data: OnboardingApprovalRequest):
    try: return CandidatePersistenceService().approve(data)
    except ValueError as exc: raise HTTPException(409, str(exc)) from exc


@router.get("/preferences", response_model=JobPreferences)
def get_preferences(): return CandidatePersistenceService().state().preferences


@router.put("/preferences", response_model=JobPreferences)
def put_preferences(data: JobPreferences): return CandidatePersistenceService().save_preferences(data)
