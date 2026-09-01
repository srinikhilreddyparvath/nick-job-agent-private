import math
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.db.models import JobFeedbackRecord,JobRecord,JobScoreRecord,SemanticAnalysisRecord
from app.models.feedback import EvaluationState,RankingEvaluation

class RankingEvaluationService:
    def __init__(self,minimum_labels:int=5): self.minimum_labels=minimum_labels
    def evaluate(self,db:Session)->RankingEvaluation:
        labels=db.scalars(select(JobFeedbackRecord)).all()
        if len(labels)<self.minimum_labels: return RankingEvaluation(state=EvaluationState.insufficient_data,labeled_jobs=len(labels),minimum_required=self.minimum_labels,message=f"At least {self.minimum_labels} human labels are required.")
        relevant={"excellent":3,"good":2,"maybe":1,"poor":0}; pairs=[]
        for label in labels:
            score=db.scalar(select(JobScoreRecord).where(JobScoreRecord.job_id==label.job_id).order_by(JobScoreRecord.created_at.desc()))
            semantic=db.scalar(select(SemanticAnalysisRecord).where(SemanticAnalysisRecord.job_id==label.job_id).order_by(SemanticAnalysisRecord.created_at.desc()))
            if score: pairs.append({"deterministic":score.overall_score,"semantic":semantic.semantic_score if semantic else None,"blended":semantic.blended_score if semantic else None,"label":relevant[label.human_label]})
        if len(pairs)<self.minimum_labels: return RankingEvaluation(state=EvaluationState.insufficient_data,labeled_jobs=len(pairs),minimum_required=self.minimum_labels,message="Enough labels exist, but not enough labeled jobs have scores.")
        def metrics_for(name):
            available=[(x[name],x["label"]) for x in pairs if x[name] is not None]
            if len(available)<self.minimum_labels:return None
            predicted=[x[0] for x in available];actual=[x[1] for x in available];mean_p=sum(predicted)/len(predicted);mean_a=sum(actual)/len(actual);denom=math.sqrt(sum((x-mean_p)**2 for x in predicted)*sum((x-mean_a)**2 for x in actual));correlation=sum((p-mean_p)*(a-mean_a) for p,a in available)/denom if denom else 0;agreement=sum((p>=70)==(a>=2) for p,a in available)/len(available);ranked=sorted(available,reverse=True);k=min(5,len(ranked));precision=sum(a>=2 for _,a in ranked[:k])/k;dcg=sum((2**a-1)/math.log2(i+2) for i,(_,a) in enumerate(ranked[:k]));ideal=sorted((a for _,a in available),reverse=True)[:k];idcg=sum((2**a-1)/math.log2(i+2) for i,a in enumerate(ideal));return {"precision_at_5":round(precision,3),"ndcg_at_5":round(dcg/idcg if idcg else 0,3),"ranking_agreement":round(agreement,3),"score_label_correlation":round(correlation,3),"calibration_high_score_relevance":round(sum(a>=2 for p,a in available if p>=80)/max(1,sum(p>=80 for p,a in available)),3)}
        metrics={name:value for name in ("deterministic","semantic","blended") if (value:=metrics_for(name)) is not None}
        return RankingEvaluation(state=EvaluationState.ready,labeled_jobs=len(pairs),minimum_required=self.minimum_labels,metrics=metrics,message="Ranking metrics are reported only for score families with enough human-labeled jobs.")
