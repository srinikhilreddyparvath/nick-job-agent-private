import json
import os
from abc import ABC, abstractmethod
from time import perf_counter
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.models.semantic import AgentToolDecision, JobResearchReport, LLMResponse, LLMUsage, SemanticFitReport, SemanticRoleClassification

T=TypeVar("T",bound=BaseModel)


class LLMError(RuntimeError): pass


class LLMProvider(ABC):
    name:str
    model:str
    @abstractmethod
    def generate(self,system:str,user:str,schema:type[T],*,max_tokens:int,temperature:float=0)->LLMResponse: ...


class MockLLMProvider(LLMProvider):
    name="mock"
    def __init__(self,model:str="mock-semantic-v1",responses:dict[str,dict]|None=None): self.model=model;self.responses=responses or {}
    def generate(self,system,user,schema,*,max_tokens,temperature=0):
        if schema.__name__ in self.responses: payload=self.responses[schema.__name__]
        elif schema is AgentToolDecision:
            context=json.loads(user);state=context.get("state",{})
            if not state.get("tool_outputs"):
                tool=context["allowed_tools"][0];payload={"action":"tool","tool_name":tool,"arguments":context.get("suggested_arguments",{}).get(tool,{})}
            else:payload={"action":"final","final_state":{"completed":True}}
        elif schema is SemanticRoleClassification: payload={"role_family":"UNKNOWN","confidence":0.45,"reasoning":"Mock classifier retains uncertainty.","signals":[]}
        elif schema is JobResearchReport:
            context=json.loads(user); payload={"job_id":context["job_id"],"company_summary":"Based only on the supplied job and company data.","role_summary":context["title"],"key_requirements":context.get("requirements",[]),"source_citations":context.get("sources",[])}
        elif schema is SemanticFitReport:
            context=json.loads(user); evidence=context.get("evidence",[]); cited=evidence[:2]; score=float(context.get("deterministic_score") or 60)
            payload={"job_id":context["job_id"],"role_family":context["role_family"],"semantic_fit_score":min(100,score+3),"confidence":.78,"strengths":[{"statement":x["statement"],"evidence_ids":[x["id"]]} for x in cited],"gaps":["Requirements without direct canonical evidence remain unverified."],"requirement_matches":[],"requirement_gaps":[],"evidence_ids":[x["id"] for x in cited],"career_transition_analysis":context.get("career_transition_notes"),"research_alignment":"Assessed from cited evidence only.","technical_alignment":"Assessed from cited evidence only.","experience_alignment":"Assessed from cited evidence only.","recommended_action":"review","reasoning_summary":"Mock semantic analysis grounded in retrieved evidence.","unsupported_claims":[],"requires_human_review":False}
        else: raise LLMError(f"Mock provider has no response for {schema.__name__}")
        schema.model_validate(payload)
        return LLMResponse(content=payload,provider=self.name,model=self.model,latency_ms=1,usage=LLMUsage(input_tokens=max(1,len(user)//4),output_tokens=max(1,len(json.dumps(payload))//4),estimated_cost=0))


class OpenAIProvider(LLMProvider):
    name="openai"
    def __init__(self,model:str,api_key:str|None=None,timeout:float=45): self.model=model;self.api_key=api_key or os.getenv("OPENAI_API_KEY");self.timeout=timeout
    def generate(self,system,user,schema,*,max_tokens,temperature=0):
        if not self.api_key: raise LLMError("OPENAI_API_KEY is not configured")
        started=perf_counter(); response=httpx.post("https://api.openai.com/v1/chat/completions",headers={"Authorization":f"Bearer {self.api_key}"},json={"model":self.model,"messages":[{"role":"system","content":system},{"role":"user","content":user}],"temperature":temperature,"max_tokens":max_tokens,"response_format":{"type":"json_schema","json_schema":{"name":schema.__name__,"strict":True,"schema":schema.model_json_schema()}}},timeout=self.timeout);response.raise_for_status();data=response.json();payload=json.loads(data["choices"][0]["message"]["content"]);usage=data.get("usage",{})
        return LLMResponse(content=payload,provider=self.name,model=self.model,latency_ms=int((perf_counter()-started)*1000),usage=LLMUsage(input_tokens=usage.get("prompt_tokens",0),output_tokens=usage.get("completion_tokens",0)))


class AnthropicProvider(LLMProvider):
    name="anthropic"
    def __init__(self,model:str,api_key:str|None=None,timeout:float=45): self.model=model;self.api_key=api_key or os.getenv("ANTHROPIC_API_KEY");self.timeout=timeout
    def generate(self,system,user,schema,*,max_tokens,temperature=0):
        if not self.api_key: raise LLMError("ANTHROPIC_API_KEY is not configured")
        instruction=system+"\nReturn JSON matching this schema: "+json.dumps(schema.model_json_schema());started=perf_counter();response=httpx.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":self.api_key,"anthropic-version":"2023-06-01"},json={"model":self.model,"system":instruction,"messages":[{"role":"user","content":user}],"temperature":temperature,"max_tokens":max_tokens},timeout=self.timeout);response.raise_for_status();data=response.json();payload=json.loads(data["content"][0]["text"]);usage=data.get("usage",{})
        return LLMResponse(content=payload,provider=self.name,model=self.model,latency_ms=int((perf_counter()-started)*1000),usage=LLMUsage(input_tokens=usage.get("input_tokens",0),output_tokens=usage.get("output_tokens",0)))


class LLMService:
    def __init__(self,provider:LLMProvider,settings:Settings|None=None): self.provider=provider;self.settings=settings or get_settings()
    def generate_structured(self,system:str,user:str,schema:type[T],temperature:float=0)->tuple[T,LLMResponse]:
        last_error=None
        for _ in range(self.settings.llm_max_retries+1):
            try:
                response=self.provider.generate(system,user,schema,max_tokens=self.settings.llm_max_tokens,temperature=temperature)
                if response.usage.estimated_cost==0:
                    response.usage.estimated_cost=round((response.usage.input_tokens*self.settings.llm_input_cost_per_million+response.usage.output_tokens*self.settings.llm_output_cost_per_million)/1_000_000,8)
                return schema.model_validate(response.content),response
            except (ValidationError,ValueError,json.JSONDecodeError,httpx.HTTPError,LLMError) as exc: last_error=exc
        raise LLMError(f"Structured LLM output failed validation: {last_error}")


def configured_llm_service(*,use_mock:bool=False,settings:Settings|None=None)->LLMService:
    settings=settings or get_settings()
    if use_mock:return LLMService(MockLLMProvider(),settings)
    if not settings.llm_enabled:raise LLMError("LLM is disabled")
    if settings.llm_provider=="openai":return LLMService(OpenAIProvider(settings.llm_model,timeout=settings.llm_timeout_seconds),settings)
    if settings.llm_provider=="anthropic":return LLMService(AnthropicProvider(settings.llm_model,timeout=settings.llm_timeout_seconds),settings)
    if settings.llm_provider=="mock":return LLMService(MockLLMProvider(settings.llm_model or "mock-semantic-v1"),settings)
    raise LLMError(f"Unsupported LLM provider: {settings.llm_provider or 'not configured'}")
