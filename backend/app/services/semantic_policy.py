from app.core.config import Settings,get_settings

class SemanticAnalysisPolicy:
    def __init__(self,settings:Settings|None=None):self.settings=settings or get_settings()
    def should_run(self,*,deterministic_score:float|None,role_family_confidence:float,shortlisted:bool=False,explicit:bool=False,high_priority_company:bool=False)->tuple[bool,str]:
        if explicit:return True,"explicit_request"
        if shortlisted:return True,"shortlisted"
        if high_priority_company:return True,"high_priority_company"
        if role_family_confidence<self.settings.llm_role_fallback_threshold:return True,"low_classification_confidence"
        if deterministic_score is not None and deterministic_score>=self.settings.llm_analysis_threshold:return True,"deterministic_threshold"
        return False,"below_semantic_analysis_policy"
