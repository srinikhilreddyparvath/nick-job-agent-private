import hashlib,json,re
from abc import ABC,abstractmethod
from datetime import datetime,timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings,get_settings
from app.db.models import CompanyRecord,CompanyResearchRecord
from app.models.semantic import JobResearchReport,ResearchResponse,ResearchSource
from app.prompts.research_agent_v1 import SYSTEM,VERSION
from app.services.agent_service import AgentRunService
from app.services.job_service import JobService
from app.services.llm_service import LLMService
from app.services.phase3_tools import build_phase3_tool_registry
from app.services.candidate_context_service import current_context, assert_current, job_version

class PublicResearchProvider(ABC):
    @abstractmethod
    def retrieve(self,urls:list[str],limit:int)->list[ResearchSource]:...
class WebSearchProvider(ABC):
    @abstractmethod
    def search(self,query:str):...
class HttpPublicResearchProvider(PublicResearchProvider):
    def retrieve(self,urls,limit):
        results=[]
        for url in urls[:limit]:
            if not url.startswith(("http://","https://")):continue
            try:
                response=httpx.get(url,timeout=15,follow_redirects=True,headers={"User-Agent":"CareerIntelligenceAgent/0.1"});response.raise_for_status();text=re.sub(r"<[^>]+>"," ",response.text);text=" ".join(text.split())[:3000];results.append(ResearchSource(url=str(response.url),title=str(response.url),source_type="public_page",excerpt=text))
            except Exception:continue
        return results
class SuppliedDataResearchProvider(PublicResearchProvider):
    def __init__(self,sources:list[ResearchSource]|None=None):self.sources=sources or []
    def retrieve(self,urls,limit):return self.sources[:limit]
class ResearchService:
    def __init__(self,llm:LLMService,provider:PublicResearchProvider|None=None,settings:Settings|None=None):self.llm=llm;self.provider=provider or HttpPublicResearchProvider();self.settings=settings or get_settings();self.jobs=JobService();self.runs=AgentRunService()
    def research(self,db:Session,job_id:int,refresh=False):
        snapshot = current_context()
        if snapshot.pending: return ResearchResponse(status="unavailable", error="Approve the replacement profile before research")
        record=self.jobs.get(db,job_id)
        if not record:return ResearchResponse(status="not_found",error="Job not found")
        job=build_phase3_tool_registry(db).invoke("research","get_job",{"job_id":job_id});company=db.scalar(select(CompanyRecord).where(CompanyRecord.canonical_name==record.canonical_company));urls=[str(job.source_url)]+([company.careers_url,company.website_url] if company else []);urls=[x for x in urls if x]
        fingerprint=hashlib.sha256(json.dumps({"job":job_version(record),"candidate_context":snapshot.key,"urls":urls,"prompt":VERSION,"provider":self.llm.provider.name,"model":self.llm.provider.model},sort_keys=True).encode()).hexdigest();cached=db.scalar(select(CompanyResearchRecord).where(CompanyResearchRecord.fingerprint==fingerprint))
        run=self.runs.start(db,"research","Research public company and role context with attribution",job_id,{"urls":urls},provider=self.llm.provider.name,model=self.llm.provider.model,prompt_version=VERSION,temperature=0)
        try:
            if cached and not refresh:
                assert_current(snapshot)
                report=JobResearchReport.model_validate(cached.report_json);report.cache_hit=True;self.runs.complete(db,run,report.model_dump(mode="json"),[{"step":1,"tool":"research_cache","status":"hit"}],sources_used=list(dict.fromkeys(x.url for x in report.source_citations)));return ResearchResponse(status="completed",report=report,agent_run_id=run.id)
            sources=self.provider.retrieve(urls,max(0,self.settings.llm_max_research_pages_per_job-1));stored=ResearchSource(url=str(job.source_url),title=f"{job.company} - {job.title}",source_type="stored_job_posting",excerpt=(job.description or job.title)[:3000]);sources=[stored,*sources][:self.settings.llm_max_research_pages_per_job]
            context={"job_id":job_id,"company":job.company,"title":job.title,"description":job.description,"requirements":job.requirements,"preferred_requirements":job.preferred_qualifications,"sources":[x.model_dump(mode="json") for x in sources]};report,response=self.llm.generate_structured(SYSTEM,json.dumps(context),JobResearchReport);allowed={x.url for x in sources};report.source_citations=[x for x in report.source_citations if x.url in allowed] or sources;report.provider=response.provider;report.model=response.model;report.prompt_version=VERSION;report.latency_ms=response.latency_ms;report.input_tokens=response.usage.input_tokens;report.output_tokens=response.usage.output_tokens;report.cached_tokens=response.usage.cached_tokens;report.estimated_cost=response.usage.estimated_cost
            assert_current(snapshot)
            saved=cached or CompanyResearchRecord(job_id=job_id,fingerprint=fingerprint,**snapshot.ownership());saved.company_id=company.id if company else None;saved.summary=report.company_summary;saved.role_context=report.role_summary;saved.sources=[x.model_dump(mode="json") for x in report.source_citations];saved.report_json=report.model_dump(mode="json");saved.provider=report.provider;saved.model=report.model;saved.prompt_version=VERSION;saved.input_tokens=report.input_tokens;saved.output_tokens=report.output_tokens;saved.cached_tokens=report.cached_tokens;saved.estimated_cost=report.estimated_cost;saved.latency_ms=report.latency_ms;saved.generated_at=datetime.now(timezone.utc);db.add(saved);db.commit();actions=[{"step":1,"tool":"get_job","status":"completed"},{"step":2,"tool":"get_public_pages","status":"completed","source_count":len(sources)},{"step":3,"tool":"generate_structured_research","status":"completed"}];self.runs.complete(db,run,report.model_dump(mode="json"),actions,sources_used=list(dict.fromkeys(x.url for x in report.source_citations)),input_tokens=report.input_tokens,output_tokens=report.output_tokens,cached_tokens=report.cached_tokens,estimated_cost=report.estimated_cost,latency_ms=report.latency_ms);return ResearchResponse(status="completed",report=report,agent_run_id=run.id)
        except Exception as exc:self.runs.fail(db,run,str(exc));return ResearchResponse(status="unavailable",error=str(exc),agent_run_id=run.id)
