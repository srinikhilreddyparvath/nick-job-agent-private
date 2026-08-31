from app.models.agent import AgentDefinition,AgentType

class AgentOrchestrator:
    """Explicit agent lifecycle boundary. Only Scout and Fit are enabled in Phase 2."""
    objective="Route observable agent runs while enforcing evidence and human-review policies."
    allowed_agents={AgentType.scout,AgentType.fit}
    def dispatch(self,agent,*args,**kwargs):
        if not agent.definition.active or agent.definition.agent_type not in self.allowed_agents: raise PermissionError(f"{agent.definition.agent_type} is inactive in Phase 2")
        return agent.run(*args,**kwargs)
