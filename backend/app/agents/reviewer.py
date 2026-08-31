from app.agents.base import DeterministicAgent,inactive_definition
from app.models.agent import AgentType
class ReviewerAgent(DeterministicAgent):
    definition=inactive_definition(AgentType.reviewer,"Validate generated claims against cited evidence",["EvidenceService","future ClaimValidator"])
    def run(self,*_args,**_kwargs): raise NotImplementedError("ReviewerAgent is inactive in Phase 2")
