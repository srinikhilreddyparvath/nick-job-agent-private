from app.core.config import Settings,get_settings
import json
from app.models.semantic import AgentToolDecision,LLMUsage

class AgentStepLimitError(RuntimeError):pass
class BoundedAgentExecutor:
    """Bounded explicit tool loop. It records actions, not private model reasoning."""
    def __init__(self,registry,settings:Settings|None=None):self.registry=registry;self.settings=settings or get_settings()
    def execute(self,agent_type:str,decide,state:dict):
        actions=[]
        for step in range(self.settings.llm_max_agent_steps):
            decision=decide(state,step)
            if decision.get("final") is not None:return decision["final"],actions
            call=decision.get("tool_call")
            if not call:raise ValueError("Agent decision has neither tool_call nor final")
            output=self.registry.invoke(agent_type,call["name"],call.get("arguments",{}));state.setdefault("tool_outputs",[]).append({"tool":call["name"],"output":output.model_dump(mode="json") if hasattr(output,"model_dump") else output});actions.append({"step":step+1,"tool":call["name"],"arguments":call.get("arguments",{}),"status":"completed"})
        raise AgentStepLimitError(f"Agent exceeded maximum of {self.settings.llm_max_agent_steps} steps")

class BoundedLLMToolExecutor:
    """Model-selected, schema-validated tool loop constrained by ToolRegistry permissions."""
    def __init__(self,registry,llm,settings:Settings|None=None):self.registry=registry;self.llm=llm;self.settings=settings or get_settings()
    def execute(self,agent_type:str,objective:str,state:dict,allowed_tools:list[str],suggested_arguments:dict|None=None,stop_after_tool:bool=False):
        actions=[];usage=LLMUsage();latency=0
        permitted={tool.name for tool in self.registry.allowed(agent_type)}
        if not set(allowed_tools)<=permitted:raise PermissionError("Agent requested tools outside its registry permissions")
        for step in range(self.settings.llm_max_agent_steps):
            prompt=json.dumps({"objective":objective,"state":state,"allowed_tools":allowed_tools,"suggested_arguments":suggested_arguments or {}})
            decision,response=self.llm.generate_structured("Choose exactly one allowed tool or return final. Do not provide private reasoning.",prompt,AgentToolDecision);usage.input_tokens+=response.usage.input_tokens;usage.output_tokens+=response.usage.output_tokens;usage.estimated_cost+=response.usage.estimated_cost;latency+=response.latency_ms
            if decision.action=="final" and (state.get("tool_outputs") or not stop_after_tool):return decision.final_state or {},actions,state,usage,latency
            if decision.action=="final" and stop_after_tool and len(allowed_tools)==1:
                decision.action="tool";decision.tool_name=allowed_tools[0]
            if decision.action!="tool" or not decision.tool_name:raise ValueError("Invalid agent tool decision")
            if decision.tool_name not in allowed_tools and len(allowed_tools)==1:decision.tool_name=allowed_tools[0]
            arguments=(suggested_arguments or {}).get(decision.tool_name,decision.arguments)
            output=self.registry.invoke(agent_type,decision.tool_name,arguments);serialized=output.model_dump(mode="json") if hasattr(output,"model_dump") else output;state.setdefault("tool_outputs",[]).append({"tool":decision.tool_name,"output":serialized});actions.append({"step":step+1,"tool":decision.tool_name,"arguments":arguments,"status":"completed","selection_method":"model_tool_choice_with_application_arguments"})
            if stop_after_tool:return {"tool_completed":decision.tool_name},actions,state,usage,latency
        raise AgentStepLimitError(f"Agent exceeded maximum of {self.settings.llm_max_agent_steps} steps")
