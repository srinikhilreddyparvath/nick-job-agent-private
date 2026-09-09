"""Workable public widget connector.

Adapted from career-ops providers/workable.mjs (MIT, copyright 2026
Santiago Fernández de Valderrama). See THIRD_PARTY_NOTICES.md.
"""
from urllib.parse import urlparse

from app.connectors.base import ConnectorError, JobConnector, plain_text
from app.models.job import Job, RemoteType


class WorkableConnector(JobConnector):
    source = "workable"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        slug = identifier.strip()
        if not slug.replace("-", "").replace("_", "").isalnum():
            raise ConnectorError("workable invalid account identifier")
        data = self.request_json("GET", f"https://apply.workable.com/api/v1/widget/accounts/{slug}",
                                 params={"details": "true"}, follow_redirects=False)
        jobs = []
        for item in data.get("jobs", []) if isinstance(data, dict) else []:
            title = str(item.get("title") or "").strip()
            raw_url = item.get("shortlink") or item.get("url")
            parsed = urlparse(str(raw_url or ""))
            if not title or parsed.scheme != "https" or parsed.hostname != "apply.workable.com":
                continue
            external_id = str(item.get("shortcode") or parsed.path.rstrip("/").split("/")[-1])
            location = ", ".join(filter(None, [item.get("city"), item.get("state"), item.get("country")])) or None
            jobs.append(Job(external_id=external_id, source=self.source, company=company, title=title,
                            location=location, remote_type=RemoteType.remote if item.get("telecommuting") else RemoteType.unspecified,
                            description=plain_text(item.get("description")), employment_type=item.get("employment_type"),
                            apply_url=raw_url, source_url=raw_url, posted_at=item.get("published_on")))
        return jobs
