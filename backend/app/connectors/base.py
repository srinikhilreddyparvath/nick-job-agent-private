from abc import ABC, abstractmethod
from datetime import datetime
import re

import httpx

from app.core.config import get_settings
from app.models.job import Job


class ConnectorError(RuntimeError):
    pass


def plain_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value or "")).strip()


class JobConnector(ABC):
    source: str

    def __init__(self) -> None:
        settings = get_settings()
        self.client = httpx.Client(timeout=settings.http_timeout_seconds, headers={"User-Agent": settings.connector_user_agent}, follow_redirects=True)

    def request_json(self, method: str, url: str, **kwargs):
        try:
            response = self.client.request(method, url, **kwargs)
            if response.status_code == 429:
                raise ConnectorError(f"{self.source} rate limit reached; retry later")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"{self.source} request failed: {exc}") from exc

    @abstractmethod
    def fetch_jobs(self, identifier: str, company: str) -> list[Job]: ...

