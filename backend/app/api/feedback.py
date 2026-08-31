from fastapi import APIRouter,Depends,HTTPException
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.db.models import JobRecord
from app.models.feedback import JobFeedbackRead,JobFeedbackWrite,RankingEvaluation
from app.services.feedback_service import FeedbackService
from app.services.evaluation_service import RankingEvaluationService
router=APIRouter(tags=["feedback"]); service=FeedbackService()
@router.get("/jobs/{job_id}/feedback",response_model=JobFeedbackRead)
def get_feedback(job_id:int,db:Session=Depends(get_db)):
    result=service.get(db,job_id)
    if not result: raise HTTPException(404,"Feedback not found")
    return result
def save(job_id:int,data:JobFeedbackWrite,db:Session):
    if not db.get(JobRecord,job_id): raise HTTPException(404,"Job not found")
    return service.upsert(db,job_id,data)
@router.post("/jobs/{job_id}/feedback",response_model=JobFeedbackRead,status_code=201)
def create_feedback(job_id:int,data:JobFeedbackWrite,db:Session=Depends(get_db)): return save(job_id,data,db)
@router.put("/jobs/{job_id}/feedback",response_model=JobFeedbackRead)
def update_feedback(job_id:int,data:JobFeedbackWrite,db:Session=Depends(get_db)): return save(job_id,data,db)
@router.get("/evaluation/ranking",response_model=RankingEvaluation)
def ranking_evaluation(db:Session=Depends(get_db)): return RankingEvaluationService().evaluate(db)
