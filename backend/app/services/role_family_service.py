import re
from abc import ABC,abstractmethod
from app.models.job import Job
from app.models.role_family import RoleFamily,RoleFamilyClassification

FAMILY_SIGNALS={
 RoleFamily.research_ai:{"titles":["research scientist","research engineer","applied scientist","machine learning scientist","ai scientist","ml research","generative ai researcher","llm research"],"domains":["applied research","research","generative ai","llm","agentic","reinforcement learning","multimodal","computer vision","nlp","ai infrastructure","ml systems"]},
 RoleFamily.data_science:{"titles":["data scientist","decision scientist","applied data scientist","product data scientist","machine learning data scientist"],"domains":["experimentation","causal inference","measurement","statistical","analytics","growth","marketplace","modeling","machine learning"]},
 RoleFamily.product_management:{"titles":["product manager","technical product manager","ai product manager","ml product manager"],"domains":["artificial intelligence"," ai ","machine learning","data science","generative ai","search","discovery","personalization","recommendation","platform","experimentation","developer platform"]}}

class RoleFamilyClassifier(ABC):
 @abstractmethod
 def classify(self,job:Job)->RoleFamilyClassification: ...
class DeterministicRoleFamilyClassifier(RoleFamilyClassifier):
 def classify(self,job:Job)->RoleFamilyClassification:
    title=f" {job.title.lower()} "; body=" ".join([job.description,*job.requirements,*job.preferred_qualifications]).lower(); results={}
    for family,signals in FAMILY_SIGNALS.items():
      title_hits=[x for x in signals["titles"] if x in title]; domain_hits=[x for x in signals["domains"] if x in f" {body} {title} "]
      score=min(1,0.65*min(1,len(title_hits))+0.12*min(3,len(domain_hits)))
      results[family]=(score,title_hits,domain_hits)
    family,(score,title_hits,domain_hits)=max(results.items(),key=lambda x:x[1][0])
    if score<0.58: return RoleFamilyClassification(role_family=RoleFamily.unknown,confidence=round(score,2),reasons=["Insufficient title and responsibility signals for a supported family"])
    reasons=[]
    if title_hits: reasons.append("Title signals: "+", ".join(title_hits[:3]))
    if domain_hits: reasons.append("Description/domain signals: "+", ".join(domain_hits[:4]))
    return RoleFamilyClassification(role_family=family,confidence=round(score,2),reasons=reasons)

