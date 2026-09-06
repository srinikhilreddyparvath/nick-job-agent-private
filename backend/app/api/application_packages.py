from pathlib import Path

from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.application_package import *
from app.services.application_package_service import ApplicationPackageService
from app.services.llm_service import LLMError,configured_llm_service

router=APIRouter(prefix="/jobs/{job_id}/application-package",tags=["application-package"])
def service(use_mock=False):return ApplicationPackageService(configured_llm_service(use_mock=use_mock))

@router.post("",response_model=PackageResponse)
def generate(job_id:int,request:PackageGenerateRequest,db:Session=Depends(get_db)):
    try:return service(request.use_mock).generate(db,job_id,request)
    except LLMError as exc:return PackageResponse(status="GENERATION_FAILED",error=str(exc))
@router.get("",response_model=ApplicationPackageRead)
def get_package(job_id:int,db:Session=Depends(get_db)):
    try:result=service(True).get(db,job_id)
    except Exception:result=None
    if not result:raise HTTPException(404,"Application package not found")
    return result
@router.post("/regenerate",response_model=PackageResponse)
def regenerate(job_id:int,request:PackageGenerateRequest,db:Session=Depends(get_db)):request.force=True;return generate(job_id,request,db)
@router.post("/review",response_model=PackageResponse)
def review(job_id:int,use_mock:bool=False,db:Session=Depends(get_db)):
    try:return service(use_mock).review(db,job_id)
    except LLMError as exc:return PackageResponse(status="REVIEW_REQUIRED",error=str(exc))
@router.post("/approve",response_model=ApplicationPackageRead)
def approve(job_id:int,request:PackageApproveRequest,db:Session=Depends(get_db)):
    try:return service(True).approve(db,job_id,request.save_reusable_answers)
    except ValueError as exc:raise HTTPException(409,str(exc))
@router.patch("/answers/{answer_id}",response_model=ApplicationPackageRead)
def edit_answer(job_id:int,answer_id:str,request:PackageEditAnswerRequest,db:Session=Depends(get_db)):
    try:return service(True).edit_answer(db,job_id,answer_id,request.answer)
    except KeyError:raise HTTPException(404,"Answer not found")
@router.patch("/cover-letter",response_model=ApplicationPackageRead)
def edit_cover(job_id:int,request:PackageEditCoverLetterRequest,db:Session=Depends(get_db)):return service(True).edit_cover_letter(db,job_id,request.cover_letter)
@router.patch("/resume-bullets/{bullet_id}",response_model=ApplicationPackageRead)
def edit_bullet(job_id:int,bullet_id:str,request:PackageEditResumeBulletRequest,db:Session=Depends(get_db)):
    try:return service(True).edit_resume_bullet(db,job_id,bullet_id,request.text)
    except KeyError:raise HTTPException(404,"Resume bullet not found")
@router.get("/tailored-resume",response_model=TailoredResumeData)
def resume_preview(job_id:int,db:Session=Depends(get_db)):return get_package(job_id,db).tailored_resume_preview
@router.get("/tailored-resume/download")
def resume_download(job_id:int,db:Session=Depends(get_db)):
    package=get_package(job_id,db);path=Path(package.tailored_resume_path or "")
    if not path.is_file():raise HTTPException(404,"Tailored resume file not found")
    return FileResponse(path,media_type="application/pdf",filename=path.name)
