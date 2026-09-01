from app.models.agent import AgentDefinition,AgentType

class AgentOrchestrator:
    """Explicit agent lifecycle boundary for deterministic Scout and semantic Fit/Research agents."""
    objective="Route observable agent runs while enforcing evidence and human-review policies."
    allowed_agents={AgentType.scout,AgentType.fit,AgentType.research}
    def dispatch(self,agent,*args,**kwargs):
        if not agent.definition.active or agent.definition.agent_type not in self.allowed_agents: raise PermissionError(f"{agent.definition.agent_type} is inactive")
        return agent.run(*args,**kwargs)
