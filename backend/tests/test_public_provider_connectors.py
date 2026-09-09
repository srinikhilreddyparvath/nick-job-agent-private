from types import SimpleNamespace

import pytest

from app.connectors.bamboohr import BambooHRConnector
from app.connectors.recruitee import RecruiteeConnector
from app.connectors.teamtailor import TeamtailorConnector
from app.connectors.workable import WorkableConnector


def connector(cls):
    return cls.__new__(cls)


def test_bamboohr_normalizes_and_skips_unidentified_rows():
    value = connector(BambooHRConnector)
    value.request_json = lambda *a, **k: {"result": [
        {"id": 42, "jobOpeningName": "Platform Engineer", "location": {"city": "Austin", "state": "TX"}, "isRemote": True},
        {"jobOpeningName": "Missing id"},
    ]}
    jobs = value.fetch_jobs("example-company", "Example Company")
    assert len(jobs) == 1
    assert jobs[0].external_id == "42"
    assert jobs[0].remote_type == "remote"
    assert str(jobs[0].apply_url).startswith("https://example-company.bamboohr.com/careers/42")


def test_recruitee_preserves_public_description_and_https_url():
    value = connector(RecruiteeConnector)
    value.request_json = lambda *a, **k: {"offers": [{"id": 7, "title": "Applied Scientist", "careers_url": "https://careers.example.test/o/scientist", "description": "<p>Model evaluation</p>", "city": "Remote", "remote": True}]}
    jobs = value.fetch_jobs("example-company", "Example Company")
    assert jobs[0].description == "Model evaluation"
    assert jobs[0].external_id == "7"


def test_workable_rejects_non_https_offer_urls():
    value = connector(RecruiteeConnector)
    value.request_json = lambda *a, **k: {"offers": [{"title": "Unsafe", "careers_url": "http://example.test/job"}]}
    assert value.fetch_jobs("example-company", "Example Company") == []


def test_workable_rejects_job_urls_outside_workable_hostname():
    value = connector(WorkableConnector)
    value.request_json = lambda *a, **k: {"jobs": [{"title": "Engineer", "shortcode": "ENG", "shortlink": "https://evil.example/job"}]}
    assert value.fetch_jobs("example-company", "Example Company") == []


def test_workable_normalizes_widget_job():
    value = connector(WorkableConnector)
    value.request_json = lambda *a, **k: {"jobs": [{"title": "Engineer", "shortcode": "ENG", "shortlink": "https://apply.workable.com/example/j/ENG/", "city": "New York", "country": "US", "published_on": "2026-08-20"}]}
    jobs = value.fetch_jobs("example", "Example Company")
    assert jobs[0].external_id == "ENG"
    assert jobs[0].location == "New York, US"


def test_teamtailor_parses_public_rss():
    xml = """<rss><channel><item><title>ML Engineer</title><link>https://jobs.example.test/jobs/ml-engineer</link><pubDate>Thu, 20 Aug 2026 12:00:00 GMT</pubDate></item></channel></rss>"""
    response = SimpleNamespace(text=xml, raise_for_status=lambda: None)
    value = connector(TeamtailorConnector)
    value.client = SimpleNamespace(get=lambda *a, **k: response)
    jobs = value.fetch_jobs("example-company", "Example Company")
    assert len(jobs) == 1
    assert jobs[0].title == "ML Engineer"


@pytest.mark.parametrize("cls,identifier", [
    (BambooHRConnector, "../unsafe"),
    (RecruiteeConnector, "https://unsafe"),
    (WorkableConnector, "../unsafe"),
    (TeamtailorConnector, "../unsafe"),
])
def test_provider_identifier_validation(cls, identifier):
    with pytest.raises(RuntimeError):
        connector(cls).fetch_jobs(identifier, "Example")
