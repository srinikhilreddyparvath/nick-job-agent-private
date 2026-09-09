"""Recruitee public offers connector.

Adapted from career-ops providers/recruitee.mjs (MIT, copyright 2026
Santiago Fernández de Valderrama). See THIRD_PARTY_NOTICES.md.
"""
from urllib.parse import urlparse

from app.connectors.base import ConnectorError, JobConnector, plain_text
from app.models.job import Job, RemoteType


class RecruiteeConnector(JobConnector):
    source = "recruitee"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        tenant = identifier.strip().lower()
        if not tenant.replace("-", "").isalnum():
            raise ConnectorError("recruitee invalid tenant identifier")
        data = self.request_json("GET", f"https://{tenant}.recruitee.com/api/offers/", follow_redirects=False)
        jobs = []
        for item in data.get("offers", []) if isinstance(data, dict) else []:
            title = str(item.get("title") or "").strip()
            raw_url = item.get("careers_url") or item.get("url")
            try:
                parsed = urlparse(str(raw_url))
            except Exception:
                continue
            if not title or parsed.scheme != "https" or not parsed.netloc:
                continue
            external_id = str(item.get("id") or parsed.path.rstrip("/").split("/")[-1])
            location = item.get("location") or ", ".join(filter(None, [item.get("city"), item.get("country")])) or None
            jobs.append(Job(external_id=external_id, source=self.source, company=company, title=title,
                            location=location, remote_type=RemoteType.remote if item.get("remote") else RemoteType.unspecified,
                            description=plain_text(item.get("description")), apply_url=raw_url, source_url=raw_url))
        return jobs
