from types import SimpleNamespace

from app.services.posting_confidence_service import posting_confidence


def job(source="greenhouse", status="LIKELY_LIVE"):
    return SimpleNamespace(source=source, posting_status=status)


def test_official_recent_observation_is_medium():
    assert posting_confidence(job())["level"] == "MEDIUM"


def test_native_live_official_source_is_high():
    assert posting_confidence(job(status="LIVE"))["level"] == "HIGH"


def test_unknown_is_not_presented_as_live():
    assert posting_confidence(job("generic_company_site", "CHECK_FAILED"))["level"] == "UNKNOWN"


def test_expired_is_low():
    assert posting_confidence(job(status="EXPIRED"))["level"] == "LOW"
