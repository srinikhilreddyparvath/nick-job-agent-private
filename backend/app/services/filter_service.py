from pydantic import BaseModel, Field

from app.models.job import Job, RemoteType
from app.models.profile import JobPreferences


class FilterResult(BaseModel):
    passes: bool
    reasons: list[str] = Field(default_factory=list)


class JobFilterService:
    """Applies only explicit hard constraints. Empty preferences impose no constraint."""

    def evaluate(self, job: Job, preferences: JobPreferences) -> FilterResult:
        title = job.title.lower(); company = job.company.lower()
        text = " ".join([job.title, job.description, *job.requirements]).lower()
        reasons: list[str] = []
        if any(item.lower() in title for item in preferences.excluded_titles): reasons.append("excluded title")
        if any(item.lower() == company for item in preferences.excluded_companies): reasons.append("excluded company")
        if preferences.required_keywords and not all(item.lower() in text for item in preferences.required_keywords): reasons.append("missing required keyword")
        if any(item.lower() in text for item in preferences.excluded_keywords): reasons.append("excluded keyword")
        if job.remote_type == RemoteType.remote and not preferences.remote_allowed: reasons.append("remote roles disabled")
        if job.remote_type == RemoteType.hybrid and not preferences.hybrid_allowed: reasons.append("hybrid roles disabled")
        if preferences.locations and job.remote_type != RemoteType.remote and not any(item.lower() in (job.location or "").lower() for item in preferences.locations): reasons.append("location outside configured list")
        if preferences.employment_types and not any(item.lower() == (job.employment_type or "").lower() for item in preferences.employment_types): reasons.append("employment type not allowed")
        if preferences.minimum_salary is not None and job.salary_max is not None and job.salary_max < preferences.minimum_salary: reasons.append("salary below minimum")
        return FilterResult(passes=not reasons, reasons=reasons)
