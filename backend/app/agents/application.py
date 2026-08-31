from app.agents.base import DeterministicAgent,inactive_definition
from app.models.agent import AgentType

class ApplicationAgent(DeterministicAgent):
    """Future material generation boundary. Submission is deliberately unavailable."""

    enabled = False
    truthfulness_rule = "Use only verified, evidence-linked candidate facts; never invent claims."
    definition=inactive_definition(AgentType.application,"Generate evidence-grounded, role-family-specific application materials without implying unsupported experience",["IdentityService","EvidenceService","RoleFamily","future generation service","future claim validator"])

    def submit(self, *_args, **_kwargs):
        raise NotImplementedError("Automatic application submission is outside Phase 1")
    def run(self,*_args,**_kwargs): raise NotImplementedError("ApplicationAgent is inactive in Phase 2")
