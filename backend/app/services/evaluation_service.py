import math
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import JobFeedbackRecord,JobRecord,JobScoreRecord
from app.models.feedback import EvaluationState,RankingEvaluation

class RankingEvaluationService:
    def __init__(self,minimum_labels:int=5): self.minimum_labels=minimum_labels
    def evaluate(self,db:Session)->RankingEvaluation:
        labels=db.scalars(select(JobFeedbackRecord)).all()
        if len(labels)<self.minimum_labels: return RankingEvaluation(state=EvaluationState.insufficient_data,labeled_jobs=len(labels),minimum_required=self.minimum_labels,message=f"At least {self.minimum_labels} human labels are required.")
        relevant={"excellent":3,"good":2,"maybe":1,"poor":0}; pairs=[]
        for label in labels:
            score=db.scalar(select(JobScoreRecord).where(JobScoreRecord.job_id==label.job_id).order_by(JobScoreRecord.created_at.desc()))
            if score: pairs.append((score.overall_score,relevant[label.human_label]))
        if len(pairs)<self.minimum_labels: return RankingEvaluation(state=EvaluationState.insufficient_data,labeled_jobs=len(pairs),minimum_required=self.minimum_labels,message="Enough labels exist, but not enough labeled jobs have scores.")
        predicted=[x[0] for x in pairs]; actual=[x[1] for x in pairs]; mean_p=sum(predicted)/len(predicted); mean_a=sum(actual)/len(actual); denom=math.sqrt(sum((x-mean_p)**2 for x in predicted)*sum((x-mean_a)**2 for x in actual)); agreement=sum((p>=70)==(a>=2) for p,a in pairs)/len(pairs)
        correlation=sum((p-mean_p)*(a-mean_a) for p,a in pairs)/denom if denom else 0
        return RankingEvaluation(state=EvaluationState.ready,labeled_jobs=len(pairs),minimum_required=self.minimum_labels,metrics={"ranking_agreement":round(agreement,3),"score_label_correlation":round(correlation,3)},message="Initial deterministic evaluation; Precision@K, Recall@K, nDCG, and calibration can build on this labeled set.")
