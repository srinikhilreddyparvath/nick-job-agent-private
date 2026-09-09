OFFICIAL_PROVIDERS = {"greenhouse", "ashby", "lever", "smartrecruiters", "workday", "workable", "bamboohr", "teamtailor", "recruitee"}


def posting_confidence(job) -> dict[str, str]:
    """Availability signal kept separate from OpportunityScore."""
    status = (getattr(job, "posting_status", None) or "UNKNOWN").upper()
    source = (getattr(job, "source", None) or "").lower()
    if status in {"EXPIRED", "NOT_FOUND", "CLOSED"}:
        return {"level": "LOW", "reason": "The official posting no longer appears active."}
    if status == "LIVE" and source in OFFICIAL_PROVIDERS:
        return {"level": "HIGH", "reason": "Available through a supported official employer source."}
    if status == "LIKELY_LIVE" and source in OFFICIAL_PROVIDERS:
        return {"level": "MEDIUM", "reason": "Recently observed through a supported official employer source."}
    return {"level": "UNKNOWN", "reason": "Current availability could not be independently verified."}
