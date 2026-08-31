from app.connectors.base import JobConnector, plain_text
from app.models.job import Job


class GreenhouseConnector(JobConnector):
    source = "greenhouse"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        data = self.request_json("GET", f"https://boards-api.greenhouse.io/v1/boards/{identifier}/jobs", params={"content": "true"})
        jobs = []
        for item in data.get("jobs", []):
            location = (item.get("location") or {}).get("name")
            description = plain_text(item.get("content"))
            jobs.append(Job(external_id=str(item["id"]), source=self.source, company=company, title=item["title"], location=location, description=description, requirements=[], preferred_qualifications=[], apply_url=item["absolute_url"], source_url=item["absolute_url"], posted_at=item.get("updated_at")))
        return jobs

