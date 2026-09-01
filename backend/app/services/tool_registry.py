from dataclasses import dataclass
from typing import Any,Callable
from pydantic import BaseModel

@dataclass(frozen=True)
class AgentTool:
    name:str;description:str;input_schema:type[BaseModel];output_schema:type[BaseModel]|None;allowed_agents:set[str];handler:Callable[...,Any];sensitive:bool=False;requires_human_approval:bool=False
class ToolRegistry:
    def __init__(self):self._tools={}
    def register(self,tool:AgentTool):
        if tool.name in self._tools:raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name]=tool
    def allowed(self,agent_type:str):return [x for x in self._tools.values() if agent_type in x.allowed_agents]
    def invoke(self,agent_type:str,name:str,arguments:dict):
        tool=self._tools.get(name)
        if not tool or agent_type not in tool.allowed_agents:raise PermissionError(f"Tool {name} is not allowed for {agent_type}")
        if tool.requires_human_approval:raise PermissionError(f"Tool {name} requires human approval")
        values=tool.input_schema.model_validate(arguments);result=tool.handler(**values.model_dump())
        return tool.output_schema.model_validate(result) if tool.output_schema else result
