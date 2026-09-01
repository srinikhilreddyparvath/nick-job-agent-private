from app.agents.base import DeterministicAgent
from app.models.agent import AgentDefinition,AgentType
from app.services.research_service import ResearchService

class ResearchAgent(DeterministicAgent):
    """Bounded, attributable public company and role research."""

    enabled = True
    definition=AgentDefinition(agent_type=AgentType.research,objective="Research company and role context from supplied or safely retrievable public sources with attribution",allowed_tools=["get_job","get_company","get_company_careers_page","get_public_job_page","get_candidate_evidence","get_existing_company_research"],input_state=["job","company registry","public source URLs"],output_state=["structured research report","source citations","agent trace"],allowed_actions=["read stored data","retrieve supplied public URLs","summarize attributed sources"],evidence_access="read-only candidate evidence and attributed public sources",failure_behavior="return available stored job context and record unavailable public sources",requires_human_review_conditions=["source conflict","unsupported research claim","access restriction"],active=True)
    def __init__(self,llm=None,provider=None):self.llm=llm;self.provider=provider
    def run(self,db,job_id,refresh=False):
        if not self.llm:raise ValueError("ResearchAgent requires an LLMService")
        return ResearchService(self.llm,self.provider).research(db,job_id,refresh)

ResearcherAgent=ResearchAgent
