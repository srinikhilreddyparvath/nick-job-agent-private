from app.agents.base import DeterministicAgent,inactive_definition
from app.models.agent import AgentType

class ResearchAgent(DeterministicAgent):
    """Reserved for evidence-backed company research in a later phase."""

    enabled = False
    definition=inactive_definition(AgentType.research,"Research companies, public careers pages, job requirements, role-family context, and candidate evidence using attributable sources",["future authorized public web research","Company registry","AtsDetector","EvidenceService","RoleFamilyClassifier"])
    def run(self,*_args,**_kwargs): raise NotImplementedError("ResearchAgent is inactive in Phase 2")

ResearcherAgent=ResearchAgent
