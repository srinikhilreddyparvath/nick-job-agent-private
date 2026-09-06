from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CareerIntelligenceRun(BaseModel):
    id: int
    status: str
    stage: str
    source_count: int = 0
    sources_scanned: int = 0
    sources_succeeded: int = 0
    sources_failed: int = 0
    companies_represented: int = 0
    jobs_found: int = 0
    unique_jobs: int = 0
    promising_jobs: int = 0
    semantic_selected: int = 0
    semantic_completed: int = 0
    semantic_failed: int = 0
    ranked_jobs: int = 0
    provider: str | None = None
    model: str | None = None
    estimated_cost: float = 0
    message: str = ""
    errors: list[dict[str, Any]] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
