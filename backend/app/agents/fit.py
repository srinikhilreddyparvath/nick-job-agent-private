from app.models.job import Job, ScoreResult
from app.models.profile import CandidateProfile, JobPreferences
from app.services.scoring_service import ScoringEngine
from app.models.agent import AgentDefinition,AgentType
from app.agents.base import DeterministicAgent
from app.services.semantic_analysis_service import SemanticAnalysisService


class FitAgent(DeterministicAgent):
    definition=AgentDefinition(agent_type=AgentType.fit,objective="Preserve deterministic fit and optionally produce a structured evidence-grounded semantic fit report",allowed_tools=["get_job","get_deterministic_score","get_role_family","search_candidate_evidence","search_semantic_evidence","get_job_preferences","get_human_feedback_history","validate_claim"],input_state=["normalized job","deterministic fit","role family","candidate evidence","preferences"],output_state=["deterministic score","semantic fit report","evidence citations","unsupported claims","agent trace"],allowed_actions=["retrieve verified evidence","analyze requirements","validate claims","score semantic fit","flag gaps"],evidence_access="read-only verified evidence IDs only",failure_behavior="return deterministic baseline and record semantic failure",requires_human_review_conditions=["unsupported claim","missing candidate fact","human classification disagreement","ambiguous legal question"],active=True)
    def __init__(self, engine: ScoringEngine): self.engine = engine
    def evaluate(self, job: Job, profile: CandidateProfile, preferences: JobPreferences) -> ScoreResult: return self.engine.score(job, profile, preferences)
    def run(self,job,profile,preferences): return self.evaluate(job,profile,preferences)
    def analyze(self,db,job_id,llm,refresh=False):return SemanticAnalysisService(llm).analyze(db,job_id,refresh)
