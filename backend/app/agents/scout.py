from app.connectors.base import JobConnector
from app.models.job import Job
from app.models.agent import AgentDefinition,AgentType
from app.agents.base import DeterministicAgent


class ScoutAgent(DeterministicAgent):
    """Orchestrates read-only discovery. It never submits applications."""

    definition=AgentDefinition(agent_type=AgentType.scout,objective="Discover normalized jobs across company registry, source registry, ATS detection, structured sites, and manual ingestion",allowed_tools=["ScanOrchestrator","AtsDetector","Company registry","JobSource registry","ATS connectors","manual URL/text ingestion"],input_state=["enabled companies","enabled job sources","optional manual job reference"],output_state=["scan run","classified normalized jobs","multi-source metrics"],allowed_actions=["inspect public ATS metadata","fetch public job data","classify","filter","deduplicate","persist","score"],evidence_access="candidate evidence is read-only during automatic scoring",failure_behavior="record explicit blocked/unsupported reason and continue other sources",requires_human_review_conditions=["CAPTCHA","login","access control","unsupported source"],active=True)
    def discover(self, connector: JobConnector, identifier: str, company: str) -> list[Job]:
        return connector.fetch_jobs(identifier=identifier, company=company)
    def run(self,orchestrator,db,sources): return orchestrator.scan(db,sources)
