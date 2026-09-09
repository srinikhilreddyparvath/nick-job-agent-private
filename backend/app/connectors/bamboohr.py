"""BambooHR public careers connector.

Adapted from career-ops providers/bamboohr.mjs (MIT, copyright 2026
Santiago Fernández de Valderrama). See THIRD_PARTY_NOTICES.md.
"""
from urllib.parse import urlparse

from app.connectors.base import ConnectorError, JobConnector
from app.models.job import Job, RemoteType


class BambooHRConnector(JobConnector):
    source = "bamboohr"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        tenant = identifier.strip().lower()
        if not tenant.replace("-", "").isalnum():
            raise ConnectorError("bamboohr invalid tenant identifier")
        origin = f"https://{tenant}.bamboohr.com"
        data = self.request_json("GET", f"{origin}/careers/list", follow_redirects=False)
        jobs = []
        for item in data.get("result", []) if isinstance(data, dict) else []:
            external_id = str(item.get("id") or "").strip()
            title = str(item.get("jobOpeningName") or "").strip()
            if not external_id or not title:
                continue
            location_data = item.get("location") or {}
            location = ", ".join(filter(None, [location_data.get("city"), location_data.get("state")])) or None
            if item.get("isRemote"):
                location = f"{location}, Remote" if location else "Remote"
            url = f"{origin}/careers/{external_id}"
            if urlparse(url).scheme != "https":
                continue
            jobs.append(Job(external_id=external_id, source=self.source, company=company, title=title,
                            location=location, remote_type=RemoteType.remote if item.get("isRemote") else RemoteType.unspecified,
                            employment_type=item.get("employmentStatusLabel"), apply_url=url, source_url=url))
        return jobs
