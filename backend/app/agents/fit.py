from app.models.job import Job, ScoreResult
from app.models.profile import CandidateProfile, JobPreferences
from app.services.scoring_service import ScoringEngine
from app.models.agent import AgentDefinition,AgentType
from app.agents.base import DeterministicAgent


class FitAgent(DeterministicAgent):
    definition=AgentDefinition(agent_type=AgentType.fit,objective="Classify role family and apply its deterministic evidence-grounded fit rubric",allowed_tools=["RoleFamilyClassifier","FamilyScoringEngine","baseline ScoringEngine","EvidenceService"],input_state=["normalized job","candidate profile","preferences"],output_state=["role family","family component scores","transition flag","evidence IDs","recommendation"],allowed_actions=["classify","retrieve evidence","score","explain","flag career transition"],evidence_access="read-only verified evidence",failure_behavior="use UNKNOWN family or return no recommendation and record error",requires_human_review_conditions=["missing candidate fact","human classification disagreement","ambiguous legal question"],active=True)
    def __init__(self, engine: ScoringEngine): self.engine = engine
    def evaluate(self, job: Job, profile: CandidateProfile, preferences: JobPreferences) -> ScoreResult: return self.engine.score(job, profile, preferences)
    def run(self,job,profile,preferences): return self.evaluate(job,profile,preferences)
