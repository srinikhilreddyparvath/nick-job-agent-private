from app.connectors.base import JobConnector,plain_text
from app.models.job import Job,RemoteType

class SmartRecruitersConnector(JobConnector):
    source="smartrecruiters"
    def fetch_jobs(self,identifier:str,company:str)->list[Job]:
        offset=0; jobs=[]
        while True:
            data=self.request_json("GET",f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings",params={"limit":100,"offset":offset})
            items=data.get("content",[])
            for summary in items:
                detail=self.request_json("GET",f"https://api.smartrecruiters.com/v1/companies/{identifier}/postings/{summary['id']}")
                location=detail.get("location") or {}; location_text=", ".join(str(location.get(x)) for x in ("city","region","country") if location.get(x)); remote=RemoteType.remote if detail.get("remote") else RemoteType.unspecified
                sections=detail.get("jobAd",{}).get("sections",{}); description=" ".join(plain_text((sections.get(x) or {}).get("text")) for x in ("jobDescription","qualifications","additionalInformation"))
                salary=detail.get("compensation") or {}; url=detail.get("postingUrl") or f"https://jobs.smartrecruiters.com/{identifier}/{detail['id']}"
                jobs.append(Job(external_id=str(detail["id"]),source=self.source,company=(detail.get("company") or {}).get("name") or company,title=detail["name"],location=location_text or None,remote_type=remote,employment_type=(detail.get("typeOfEmployment") or {}).get("label"),salary_min=salary.get("min"),salary_max=salary.get("max"),salary_currency=salary.get("currency"),description=description,requirements=[plain_text((sections.get("qualifications") or {}).get("text"))] if sections.get("qualifications") else [],preferred_qualifications=[],apply_url=url,source_url=url,posted_at=detail.get("releasedDate")))
            offset+=len(items)
            if not items or offset>=data.get("totalFound",offset): break
        return jobs
