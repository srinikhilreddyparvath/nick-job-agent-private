import json,re
from urllib.parse import urljoin
from app.connectors.base import JobConnector,ConnectorError,plain_text
from app.models.job import Job,RemoteType

def _values(value): return value if isinstance(value,list) else [value] if value else []
def _location(data):
    places=[]
    for item in _values(data.get("jobLocation")):
        address=item.get("address",{}) if isinstance(item,dict) else {}; text=", ".join(str(address.get(x)) for x in ("addressLocality","addressRegion","addressCountry") if address.get(x));
        if text: places.append(text)
    if data.get("jobLocationType")=="TELECOMMUTE": return "Remote",RemoteType.remote
    return "; ".join(places) or None,RemoteType.unspecified
def _salary(data):
    salary=data.get("baseSalary") or {}; currency=data.get("salaryCurrency") or (salary.get("currency") if isinstance(salary,dict) else None); value=salary.get("value",salary) if isinstance(salary,dict) else salary
    if isinstance(value,dict): return value.get("minValue") or value.get("value"),value.get("maxValue") or value.get("value"),currency or value.get("currency")
    return (value,value,currency) if isinstance(value,(int,float)) else (None,None,currency)
def parse_jobposting(data:dict,page_url:str,default_company:str|None=None,source:str="generic_company_site")->Job:
    title=data.get("title") or data.get("name"); url=urljoin(page_url,data.get("url") or page_url); org=data.get("hiringOrganization") or {}; company=org.get("name") if isinstance(org,dict) else str(org); location,remote=_location(data); low,high,currency=_salary(data); identifier=data.get("identifier"); external=str(identifier.get("value") if isinstance(identifier,dict) else identifier or url)
    if not title: raise ConnectorError("structured_job_missing_title")
    qualifications=plain_text(data.get("qualifications") if isinstance(data.get("qualifications"),str) else "")
    return Job(external_id=external,source=source,company=company or default_company or "Unknown company",title=title,location=location,remote_type=remote,employment_type=", ".join(_values(data.get("employmentType"))) or None,salary_min=low,salary_max=high,salary_currency=currency,description=plain_text(data.get("description")),requirements=[qualifications] if qualifications else [],preferred_qualifications=[],apply_url=url,source_url=page_url,posted_at=data.get("datePosted"))
def extract_jsonld_jobs(html:str,page_url:str,default_company:str|None=None,source:str="generic_company_site")->list[Job]:
    results=[]
    for raw in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',html,re.I|re.S):
      try: payload=json.loads(raw.strip())
      except json.JSONDecodeError: continue
      nodes=payload if isinstance(payload,list) else payload.get("@graph",[payload]) if isinstance(payload,dict) else []
      for node in nodes:
        types=_values(node.get("@type")) if isinstance(node,dict) else []
        if "JobPosting" in types:
          try: results.append(parse_jobposting(node,page_url,default_company,source))
          except ConnectorError: continue
    return results
class GenericCompanySiteConnector(JobConnector):
    source="generic_company_site"
    def fetch_jobs(self,identifier:str,company:str)->list[Job]:
        try: response=self.client.get(identifier); response.raise_for_status()
        except Exception as exc: raise ConnectorError(f"generic_site_fetch_failed: {exc}") from exc
        jobs=extract_jsonld_jobs(response.text,str(response.url),company)
        if jobs:return jobs
        links={urljoin(str(response.url),x) for x in re.findall(r'href=["\']([^"\']+)["\']',response.text,re.I) if any(k in x.lower() for k in ("/job/","/jobs/","career"))}
        for link in list(links)[:50]:
          try: detail=self.client.get(link); detail.raise_for_status(); jobs.extend(extract_jsonld_jobs(detail.text,str(detail.url),company))
          except Exception: continue
        if not jobs: raise ConnectorError("no_structured_job_postings_found")
        return jobs
