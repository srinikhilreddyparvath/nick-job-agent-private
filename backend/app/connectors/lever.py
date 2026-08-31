from app.connectors.base import JobConnector, plain_text
from app.models.job import Job


class LeverConnector(JobConnector):
    source = "lever"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        data = self.request_json("GET", f"https://api.lever.co/v0/postings/{identifier}", params={"mode": "json"})
        jobs = []
        for item in data:
            categories = item.get("categories") or {}
            description = plain_text(" ".join([item.get("descriptionPlain") or "", *[section.get("content", "") for section in item.get("lists", [])]]))
            jobs.append(Job(external_id=item["id"], source=self.source, company=company, title=item["text"], location=categories.get("location"), employment_type=categories.get("commitment"), description=description, requirements=[], preferred_qualifications=[], apply_url=item.get("applyUrl") or item["hostedUrl"], source_url=item["hostedUrl"], posted_at=None))
        return jobs

