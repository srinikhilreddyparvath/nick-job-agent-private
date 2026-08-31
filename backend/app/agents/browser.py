from app.agents.base import DeterministicAgent,inactive_definition
from app.models.agent import AgentType
class BrowserAgent(DeterministicAgent):
    definition=inactive_definition(AgentType.browser,"Prepare and eventually fill supported application forms",["IdentityService","future Playwright browser","ClaimValidator"])
    def run(self,*_args,**_kwargs): raise NotImplementedError("BrowserAgent is inactive; Playwright is not installed")
