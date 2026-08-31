from enum import StrEnum
from pydantic import BaseModel,Field

class RoleFamily(StrEnum):
    research_ai="RESEARCH_AI"; data_science="DATA_SCIENCE"; product_management="PRODUCT_MANAGEMENT"; unknown="UNKNOWN"
class ClassificationMethod(StrEnum): deterministic_rules="deterministic_rules"; human_override="human_override"; future_llm="future_llm"
class RoleFamilyClassification(BaseModel):
    role_family:RoleFamily; confidence:float=Field(ge=0,le=1); reasons:list[str]; classification_method:ClassificationMethod=ClassificationMethod.deterministic_rules
class FamilyFitResult(BaseModel):
    role_family:RoleFamily; family_fit_score:float=Field(ge=0,le=100); family_component_scores:dict[str,dict]; strengths:list[str]; gaps:list[str]; matched_evidence_ids:list[str]; recommendation:str; career_transition_flag:bool=False; career_transition_notes:str|None=None
