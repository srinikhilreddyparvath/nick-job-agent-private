from app.connectors.base import JobConnector, plain_text
from app.models.job import Job, RemoteType


class AshbyConnector(JobConnector):
    source = "ashby"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        data = self.request_json("POST", "https://api.ashbyhq.com/posting-api/job-board", json={"organizationHostedJobsPageName": identifier})
        jobs = []
        for item in data.get("jobs", []):
            remote = RemoteType.remote if item.get("isRemote") else RemoteType.unspecified
            jobs.append(Job(external_id=item["id"], source=self.source, company=company, title=item["title"], location=item.get("location"), remote_type=remote, employment_type=item.get("employmentType"), description=plain_text(item.get("descriptionHtml") or item.get("descriptionPlain")), requirements=[], preferred_qualifications=[], apply_url=item["applyUrl"], source_url=item.get("jobUrl") or item["applyUrl"], posted_at=item.get("publishedAt")))
        return jobs

