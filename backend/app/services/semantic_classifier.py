import json
from app.core.config import Settings,get_settings
from app.models.job import Job
from app.models.semantic import ResolvedRoleClassification,SemanticRoleClassification
from app.prompts.role_classifier_v1 import SYSTEM
from app.services.llm_service import LLMService
from app.services.role_family_service import DeterministicRoleFamilyClassifier

class SemanticRoleFamilyClassifier:
    def __init__(self,llm:LLMService):self.llm=llm
    def classify(self,job:Job)->SemanticRoleClassification:
        value,_=self.llm.generate_structured(SYSTEM,json.dumps({"title":job.title,"description":job.description,"requirements":job.requirements,"preferred_qualifications":job.preferred_qualifications}),SemanticRoleClassification);return value
class RoleClassificationPolicy:
    def __init__(self,semantic:SemanticRoleFamilyClassifier|None=None,settings:Settings|None=None):self.deterministic=DeterministicRoleFamilyClassifier();self.semantic=semantic;self.settings=settings or get_settings()
    def classify(self,job:Job)->ResolvedRoleClassification:
        baseline=self.deterministic.classify(job)
        if baseline.confidence>=self.settings.llm_role_fallback_threshold or not self.semantic:return ResolvedRoleClassification(deterministic_family=baseline.role_family,deterministic_confidence=baseline.confidence,final_family=baseline.role_family,classification_resolution_method="deterministic_precedence")
        semantic=self.semantic.classify(job);final=semantic.role_family if semantic.confidence>=self.settings.llm_role_fallback_threshold else baseline.role_family
        return ResolvedRoleClassification(deterministic_family=baseline.role_family,deterministic_confidence=baseline.confidence,semantic_family=semantic.role_family,semantic_confidence=semantic.confidence,final_family=final,classification_resolution_method="semantic_fallback" if final==semantic.role_family else "deterministic_low_confidence_retained")
