import json
import os
from abc import ABC, abstractmethod
from time import perf_counter
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings
from app.models.semantic import AgentToolDecision, JobResearchReport, LLMResponse, LLMUsage, SemanticFitReport, SemanticRoleClassification
from app.models.application_package import ApplicationDraft,ApplicationGenerationDraft,ApplicationReview

T=TypeVar("T",bound=BaseModel)


class LLMError(RuntimeError): pass
class StructuredOutputError(LLMError): pass
class OutputTruncatedError(StructuredOutputError): pass
class ProviderTimeoutError(LLMError): pass
class ProviderUnavailableError(LLMError): pass


def _strict_json_schema(schema:type[BaseModel])->dict:
    """Convert Pydantic JSON Schema to OpenAI's strict Structured Outputs subset."""
    result=schema.model_json_schema()
    def visit(node):
        if isinstance(node,dict):
            # OpenAI's strict JSON Schema subset rejects Pydantic's URI format
            # annotation and schema defaults. Runtime Pydantic validation still
            # enforces URL types after the provider returns the payload.
            if node.get("format") == "uri": node.pop("format")
            node.pop("default", None)
            if node.get("type")=="object" or "properties" in node:
                properties=node.get("properties",{})
                node["additionalProperties"]=False
                node["required"]=list(properties)
            for value in node.values():visit(value)
        elif isinstance(node,list):
            for value in node:visit(value)
    visit(result)
    return result


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
        elif schema in (ApplicationDraft,ApplicationGenerationDraft):
            c=json.loads(user);ev=c["evidence"];first=ev[0];questions=c.get("questions",[])
            payload={"strategy":{"job_id":c["job_id"],"target_role_family":c["role_family"],"primary_positioning":"Evidence-grounded search and ML research professional","top_3_themes":["search and retrieval","evaluation","cross-functional ML"],"top_requirements_to_emphasize":["search quality"],"known_gaps":["Unsupported requirements remain gaps"],"resume_emphasis":["verified search work"],"resume_deemphasis":[],"cover_letter_recommended":False,"application_risk":"medium","recommended_action":"human_review"},"requirements":c.get("requirements",[]),"summary":[{"text":first["statement"],"evidence_ids":[first["id"]]}],"resume_bullets":[{"id":"BULLET_001","section":"experience","employer_or_context":f'{first.get("company") or "Professional Experience"} | {first.get("role") or ""}',"generated_text":first["statement"],"source_evidence_ids":[first["id"]],"source_resume_text":first["statement"],"transformation_type":"UNCHANGED"}],"skills":[{"text":skill,"evidence_ids":[x["id"]]} for x in ev for skill in x.get("skills",[])][:12],"application_answers":[{"id":f'ANSWER_{i+1:03}',"question_text":q["question_text"],"required":q.get("required",True),"detected_category":"experience","answer":first["statement"],"original_model_answer":first["statement"],"answer_status":"DRAFT","answer_type":"EVIDENCE_GENERATED","evidence_ids":[first["id"]],"confidence":.8,"requires_human_review":False,"reusable":False} for i,q in enumerate(questions)],"cover_letter":None,"cover_letter_evidence_ids":[],"recruiter_summary":[{"text":first["statement"],"evidence_ids":[first["id"]]}]}
        elif schema is ApplicationReview:
            c=json.loads(user);blocking=c.get("deterministic_findings",[]);payload={"status":"FAIL" if blocking else "PASS","findings":blocking,"reasoning_summary":"Mock independent review completed against canonical evidence and approved policies.","requires_human_review":bool(blocking)}
        elif schema.__name__ == "ResumeExtractionPayload":
            c=json.loads(user);source=c.get("source_document","resume.txt");text=c.get("resume_text","");lines=[line.strip() for line in text.splitlines() if line.strip()];span=next((line for line in lines if len(line)>=20),lines[0] if lines else "")
            payload={"professional_name":lines[0] if lines else None,"professional_summary":{"value":span,"source_section":"resume","supporting_text":span,"confidence":.8},"employment":[],"skills":[],"education":[],"projects":[],"certifications":[],"domains":[],"technologies":[],"warnings":[]}
        else: raise LLMError(f"Mock provider has no response for {schema.__name__}")
        return LLMResponse(content=payload,provider=self.name,model=self.model,latency_ms=1,usage=LLMUsage(input_tokens=max(1,len(user)//4),output_tokens=max(1,len(json.dumps(payload))//4),estimated_cost=0))


class OpenAIProvider(LLMProvider):
    name="openai"
    def __init__(self,model:str,api_key:str|None=None,timeout:float=45): self.model=model;self.api_key=api_key or os.getenv("OPENAI_API_KEY");self.timeout=timeout
    def generate(self,system,user,schema,*,max_tokens,temperature=0):
        if not self.api_key: raise LLMError("OPENAI_API_KEY is not configured")
        started=perf_counter()
        try: response=httpx.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {self.api_key}"},json={"model":self.model,"instructions":system,"input":user,"max_output_tokens":max_tokens,"store":False,"text":{"format":{"type":"json_schema","name":schema.__name__,"strict":True,"schema":_strict_json_schema(schema)}}},timeout=self.timeout)
        except httpx.TimeoutException as exc:raise ProviderTimeoutError(f"PROVIDER_TIMEOUT timeout_seconds={self.timeout}") from exc
        except httpx.HTTPError as exc:raise ProviderUnavailableError("PROVIDER_UNAVAILABLE transport_error") from exc
        try: response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error=(response.json().get("error") or {}) if response.headers.get("content-type","").startswith("application/json") else {}
            safe=" ".join(f"{key}={error.get(key)}" for key in ("type","code","param","message") if error.get(key))
            raise StructuredOutputError(f"PROVIDER_REQUEST_FAILED status={response.status_code}{' '+safe if safe else ''}") from exc
        data=response.json();usage=data.get("usage",{});cached=(usage.get("input_tokens_details") or {}).get("cached_tokens",0);status=data.get("status");reason=(data.get("incomplete_details") or {}).get("reason")
        if status=="incomplete" or reason=="max_output_tokens":
            raise OutputTruncatedError(f"OUTPUT_TRUNCATED status={status} reason={reason or 'unknown'} output_tokens={usage.get('output_tokens',0)} max_output_tokens={max_tokens}")
        texts=[content.get("text","") for item in data.get("output",[]) if item.get("type")=="message" for content in item.get("content",[]) if content.get("type")=="output_text"]
        try:payload=json.loads("".join(texts))
        except json.JSONDecodeError as exc:raise StructuredOutputError(f"MALFORMED_STRUCTURED_OUTPUT: {exc}") from exc
        return LLMResponse(content=payload,provider=self.name,model=self.model,latency_ms=int((perf_counter()-started)*1000),usage=LLMUsage(input_tokens=usage.get("input_tokens",0),output_tokens=usage.get("output_tokens",0),cached_tokens=cached),response_status=status,incomplete_reason=reason)


class AnthropicProvider(LLMProvider):
    name="anthropic"
    def __init__(self,model:str,api_key:str|None=None,timeout:float=45): self.model=model;self.api_key=api_key or os.getenv("ANTHROPIC_API_KEY");self.timeout=timeout
    def generate(self,system,user,schema,*,max_tokens,temperature=0):
        if not self.api_key: raise LLMError("ANTHROPIC_API_KEY is not configured")
        instruction=system+"\nReturn JSON matching this schema: "+json.dumps(schema.model_json_schema());started=perf_counter();response=httpx.post("https://api.anthropic.com/v1/messages",headers={"x-api-key":self.api_key,"anthropic-version":"2023-06-01"},json={"model":self.model,"system":instruction,"messages":[{"role":"user","content":user}],"temperature":temperature,"max_tokens":max_tokens},timeout=self.timeout);response.raise_for_status();data=response.json();payload=json.loads(data["content"][0]["text"]);usage=data.get("usage",{})
        return LLMResponse(content=payload,provider=self.name,model=self.model,latency_ms=int((perf_counter()-started)*1000),usage=LLMUsage(input_tokens=usage.get("input_tokens",0),output_tokens=usage.get("output_tokens",0)))


class LLMService:
    def __init__(self,provider:LLMProvider,settings:Settings|None=None): self.provider=provider;self.settings=settings or get_settings()
    def generate_structured(self,system:str,user:str,schema:type[T],temperature:float=0,*,max_tokens:int|None=None)->tuple[T,LLMResponse]:
        last_error=None
        for _ in range(self.settings.llm_max_retries+1):
            try:
                response=self.provider.generate(system,user,schema,max_tokens=max_tokens or self.settings.llm_max_tokens,temperature=temperature)
                if response.usage.estimated_cost==0:
                    response.usage.estimated_cost=round((response.usage.input_tokens*self.settings.llm_input_cost_per_million+response.usage.output_tokens*self.settings.llm_output_cost_per_million)/1_000_000,8)
                payload=dict(response.content or {})
                for key,value in list(payload.items()):
                    field=schema.model_fields.get(key)
                    if value=="" and field is not None and not field.is_required():payload.pop(key)
                return schema.model_validate(payload),response
            except (ValidationError,ValueError,json.JSONDecodeError,httpx.HTTPError,LLMError) as exc: last_error=exc
        if isinstance(last_error,LLMError):raise last_error
        if isinstance(last_error,ValidationError):raise StructuredOutputError(f"SCHEMA_VALIDATION_FAILED fields={','.join('.'.join(map(str,item['loc'])) for item in last_error.errors()[:5])}") from last_error
        raise StructuredOutputError(f"STRUCTURED_OUTPUT_FAILED category={type(last_error).__name__}") from last_error


def configured_llm_service(*,use_mock:bool=False,settings:Settings|None=None,timeout:float|None=None)->LLMService:
    settings=settings or get_settings()
    if use_mock:return LLMService(MockLLMProvider(),settings)
    if not settings.llm_enabled:raise LLMError("LLM is disabled")
    if settings.llm_provider=="openai":return LLMService(OpenAIProvider(settings.llm_model,api_key=settings.openai_api_key.get_secret_value() if settings.openai_api_key else None,timeout=timeout or settings.llm_timeout_seconds),settings)
    if settings.llm_provider=="anthropic":return LLMService(AnthropicProvider(settings.llm_model,api_key=settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None,timeout=timeout or settings.llm_timeout_seconds),settings)
    if settings.llm_provider=="mock":return LLMService(MockLLMProvider(settings.llm_model or "mock-semantic-v1"),settings)
    raise LLMError(f"Unsupported LLM provider: {settings.llm_provider or 'not configured'}")
