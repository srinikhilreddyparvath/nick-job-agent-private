from app.connectors.base import JobConnector,ConnectorError,plain_text
from app.models.job import Job
class WorkdayConnector(JobConnector):
    source="workday"
    def fetch_jobs(self,identifier:str,company:str)->list[Job]:
        parts=identifier.split("|",2)
        if len(parts)!=3: raise ConnectorError("workday_configuration_required: board_identifier must be tenant|site|career_base_url")
        tenant,site,base=parts; endpoint=f"{base.rstrip('/')}/wday/cxs/{tenant}/{site}/jobs"; offset=0;jobs=[]
        while True:
            data=self.request_json("POST",endpoint,json={"appliedFacets":{},"limit":20,"offset":offset,"searchText":""}); items=data.get("jobPostings",[])
            for item in items:
                url=base.rstrip("/")+item.get("externalPath",""); posted=item.get("postedOn"); posted=posted if posted and len(posted)>=10 and posted[:4].isdigit() else None; jobs.append(Job(external_id=str(item.get("bulletFields",[url])[0]),source=self.source,company=company,title=item.get("title","Unknown role"),location=item.get("locationsText"),description=plain_text(item.get("jobDescription")),requirements=[],preferred_qualifications=[],apply_url=url,source_url=url,posted_at=posted))
            offset+=len(items)
            if not items or offset>=data.get("total",offset):break
        return jobs
