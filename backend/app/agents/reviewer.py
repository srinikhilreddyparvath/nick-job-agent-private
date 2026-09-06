from app.agents.base import DeterministicAgent
from app.models.agent import AgentDefinition,AgentType
class ReviewerAgent(DeterministicAgent):
    definition=AgentDefinition(agent_type=AgentType.reviewer,objective="Verify application package accuracy, grounding, consistency, and safety",allowed_tools=["get_application_package","get_candidate_evidence","get_candidate_identity","get_work_authorization_policy","get_job","get_fit_analysis","get_research_report","validate_claim","compare_resume_to_evidence"],input_state=["application package"],output_state=["structured review"],allowed_actions=["retrieve","compare","validate","approve_for_human_review","fail"],evidence_access="read-only canonical evidence",failure_behavior="leave package REVIEW_REQUIRED",requires_human_review_conditions=["unsupported claim","identity mismatch","policy ambiguity","review failure"],active=True)
    def __init__(self,service=None):self.service=service
    def run(self,db,job_id):return self.service.review(db,job_id)
