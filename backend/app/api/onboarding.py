from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.models.onboarding import OnboardingApprovalRequest, OnboardingState, ResumeIngestionResult
from app.models.profile import JobPreferences
from app.services.candidate_extraction_service import CandidateExtractionService, ResumeExtractionError
from app.services.candidate_persistence_service import CandidatePersistenceService
from app.services.llm_service import LLMError


router = APIRouter(prefix="/onboarding", tags=["onboarding"])


@router.get("", response_model=OnboardingState)
def get_onboarding_state(): return CandidatePersistenceService().state()


@router.post("/resume", response_model=ResumeIngestionResult)
def ingest_resume(file: UploadFile = File(...), use_mock: bool = Form(False)):
    try: return CandidateExtractionService().ingest(file, use_mock=use_mock)
    except ResumeExtractionError as exc: raise HTTPException(422, str(exc)) from exc
    except LLMError as exc: raise HTTPException(503,{"code":getattr(exc,"safe_category","AI_EXTRACTION_FAILED"),"message":"Your resume was saved, but AI extraction could not be completed. You can retry without uploading it again."}) from exc


@router.post("/resume/retry",response_model=ResumeIngestionResult)
def retry_resume_extraction(use_mock:bool=False):
    try:return CandidateExtractionService().retry_latest(use_mock=use_mock)
    except ResumeExtractionError as exc:raise HTTPException(422,str(exc)) from exc
    except LLMError as exc:raise HTTPException(503,{"code":getattr(exc,"safe_category","AI_EXTRACTION_FAILED"),"message":"Your resume remains saved, but AI extraction could not be completed. Please retry later."}) from exc


@router.put("/approve", response_model=OnboardingState)
def approve_onboarding(data: OnboardingApprovalRequest): return CandidatePersistenceService().approve(data)


@router.get("/preferences", response_model=JobPreferences)
def get_preferences(): return CandidatePersistenceService().state().preferences


@router.put("/preferences", response_model=JobPreferences)
def put_preferences(data: JobPreferences): return CandidatePersistenceService().save_preferences(data)
