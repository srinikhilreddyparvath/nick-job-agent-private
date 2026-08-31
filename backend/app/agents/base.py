from abc import ABC,abstractmethod
from app.models.agent import AgentDefinition

class DeterministicAgent(ABC):
    definition:AgentDefinition
    @abstractmethod
    def run(self,*args,**kwargs): ...

def inactive_definition(agent_type,objective,allowed_tools):
    return AgentDefinition(agent_type=agent_type,objective=objective,allowed_tools=allowed_tools,input_state=["future task state"],output_state=["reviewable result"],allowed_actions=["analyze only"],evidence_access="read-only verified evidence",failure_behavior="fail closed and record error",requires_human_review_conditions=["unsupported claim","ambiguous legal field","sensitive field","CAPTCHA or access block"],active=False)

