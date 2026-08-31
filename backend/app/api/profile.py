from fastapi import APIRouter, HTTPException

from app.models.profile import CandidateProfile, EvidenceRecord
from app.models.identity import IdentityFieldMapping
from app.models.policy import WorkAuthorizationAssessment
from app.services.evidence_service import EvidenceService
from app.services.identity_service import IdentityService
from app.services.policy_service import WorkAuthorizationService
from app.services.profile_service import load_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=CandidateProfile)
def get_profile() -> CandidateProfile:
    return load_profile()


@router.get("/identity/map", response_model=IdentityFieldMapping)
def map_identity_field(field_label: str, required: bool = True) -> IdentityFieldMapping:
    return IdentityService().map_form_field(field_label, required)


@router.get("/evidence",response_model=list[EvidenceRecord])
def list_evidence(company:str|None=None,domain:str|None=None,skill:str|None=None,category:str|None=None,text_query:str|None=None):
    return EvidenceService().search(company=company,domains=[domain] if domain else None,skills=[skill] if skill else None,category=category,text_query=text_query)


@router.get("/evidence/{evidence_id}",response_model=EvidenceRecord)
def get_evidence(evidence_id:str):
    result=EvidenceService().get_by_id(evidence_id)
    if not result: raise HTTPException(404,"Evidence not found")
    return result


@router.get("/work-authorization/assess",response_model=WorkAuthorizationAssessment)
def assess_work_authorization(question:str): return WorkAuthorizationService().assess(question)
