from app.agents.base import DeterministicAgent
from app.models.agent import AgentDefinition,AgentType

class ApplicationAgent(DeterministicAgent):
    """Future material generation boundary. Submission is deliberately unavailable."""

    enabled = True
    truthfulness_rule = "Use only verified, evidence-linked candidate facts; never invent claims."
    definition=AgentDefinition(agent_type=AgentType.application,objective="Create the strongest truthful draft application package using verified evidence",allowed_tools=["get_job","get_job_research","get_fit_analysis","get_candidate_profile","get_candidate_identity","get_work_authorization_policy","search_candidate_evidence","search_semantic_evidence","search_hybrid_evidence","get_master_resume","get_answer_bank","get_previous_approved_answer","create_resume_strategy","create_application_answer_draft"],input_state=["job","fit analysis","research","manual questions"],output_state=["draft application package"],allowed_actions=["retrieve","draft","validate","render"],evidence_access="read-only canonical evidence",failure_behavior="fail closed as GENERATION_FAILED",requires_human_review_conditions=["unsupported claim","ambiguous legal field","missing information","years or salary uncertainty"],active=True)

    def submit(self, *_args, **_kwargs):
        raise NotImplementedError("Automatic application submission is outside Phase 1")
    def __init__(self,service=None):self.service=service
    def run(self,db,job_id,request):return self.service.generate(db,job_id,request)
