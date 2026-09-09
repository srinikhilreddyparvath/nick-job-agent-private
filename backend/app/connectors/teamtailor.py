"""Teamtailor public RSS connector.

Adapted from career-ops providers/teamtailor.mjs (MIT, copyright 2026
Santiago Fernández de Valderrama). See THIRD_PARTY_NOTICES.md.
"""
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlparse
from xml.etree import ElementTree

from app.connectors.base import ConnectorError, JobConnector
from app.models.job import Job


class TeamtailorConnector(JobConnector):
    source = "teamtailor"

    def fetch_jobs(self, identifier: str, company: str) -> list[Job]:
        tenant = identifier.strip().lower()
        if not tenant.replace("-", "").isalnum():
            raise ConnectorError("teamtailor invalid tenant identifier")
        url = f"https://{tenant}.teamtailor.com/jobs.rss"
        try:
            response = self.client.get(url, follow_redirects=False)
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
        except Exception as exc:
            raise ConnectorError(f"teamtailor request failed: {exc}") from exc
        jobs = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            raw_url = (item.findtext("link") or "").strip()
            parsed = urlparse(raw_url)
            if not title or parsed.scheme != "https" or not parsed.netloc:
                continue
            external_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", parsed.path.strip("/"))[-255:] or raw_url
            published = item.findtext("pubDate")
            try:
                posted_at = parsedate_to_datetime(published) if published else None
            except (TypeError, ValueError):
                posted_at = None
            jobs.append(Job(external_id=external_id, source=self.source, company=company, title=title,
                            apply_url=raw_url, source_url=raw_url, posted_at=posted_at))
        return jobs
