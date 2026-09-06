import json

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models.application_package import ApplicationGenerationDraft
from app.models.semantic import LLMResponse, LLMUsage
from app.services.llm_service import (
    LLMError,
    LLMProvider,
    LLMService,
    OpenAIProvider,
    OutputTruncatedError,
    StructuredOutputError,
)
from app.db.database import SessionLocal
from app.db.models import AgentRunRecord, ApplicationPackageRecord, BrowserApplicationEventRecord
from app.services.application_package_service import ApplicationPackageService


VALID = {
    "strategy": {
        "job_id": 2,
        "target_role_family": "RESEARCH_AI",
        "primary_positioning": "Search ranking engineer",
        "top_3_themes": ["ranking"],
    },
    "summary": [],
    "resume_bullets": [],
    "skills": [],
    "application_answers": [],
    "cover_letter": None,
    "cover_letter_evidence_ids": [],
    "recruiter_summary": [],
}


class SequenceProvider(LLMProvider):
    name = "sequence"
    model = "fixture"

    def __init__(self, values):
        self.values = iter(values)
        self.calls = 0

    def generate(self, system, user, schema, *, max_tokens, temperature=0):
        self.calls += 1
        value = next(self.values)
        if isinstance(value, Exception):
            raise value
        return LLMResponse(content=value, provider=self.name, model=self.model, usage=LLMUsage())


def service(provider):
    settings = get_settings().model_copy(update={"llm_max_retries": 1})
    return LLMService(provider, settings)


def test_valid_structured_response_uses_one_attempt():
    provider = SequenceProvider([VALID])
    draft, _ = service(provider).generate_structured("system", "{}", ApplicationGenerationDraft)
    assert draft.strategy.job_id == 2
    assert provider.calls == 1


def test_malformed_then_valid_is_retried_once():
    provider = SequenceProvider([StructuredOutputError("unterminated JSON"), VALID])
    draft, _ = service(provider).generate_structured("system", "{}", ApplicationGenerationDraft)
    assert draft.strategy.job_id == 2
    assert provider.calls == 2


def test_truncated_then_valid_is_retried_without_partial_result():
    provider = SequenceProvider([OutputTruncatedError("OUTPUT_TRUNCATED"), VALID])
    draft, _ = service(provider).generate_structured("system", "{}", ApplicationGenerationDraft)
    assert draft.strategy.job_id == 2
    assert provider.calls == 2


def test_all_formatting_attempts_fail_cleanly():
    provider = SequenceProvider([StructuredOutputError("bad one"), OutputTruncatedError("bad two")])
    with pytest.raises(LLMError, match="bad two"):
        service(provider).generate_structured("system", "{}", ApplicationGenerationDraft)
    assert provider.calls == 2


def test_all_retries_fail_without_package_reviewer_or_browser_activity(client, monkeypatch):
    job = client.post("/jobs/ingest-text", json={
        "source_url": "https://public.example/jobs/format-failure",
        "company": "Fixture",
        "title": "Research Engineer",
        "location": "San Francisco, CA",
        "job_description_text": "Research and evaluate search ranking systems using Python.",
    }).json()["job"]
    client.post(f"/jobs/{job['id']}/analyze", json={"use_mock": True})
    client.post(f"/jobs/{job['id']}/research", json={"use_mock": True})
    provider = SequenceProvider([StructuredOutputError("bad one"), OutputTruncatedError("bad two")])
    monkeypatch.setattr(
        "app.api.application_packages.service",
        lambda use_mock=False: ApplicationPackageService(service(provider)),
    )
    result = client.post(f"/jobs/{job['id']}/application-package", json={"questions": []}).json()
    assert result["status"] == "GENERATION_FAILED"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(ApplicationPackageRecord).where(ApplicationPackageRecord.job_id == job["id"])) == 0
        assert db.scalar(select(func.count()).select_from(AgentRunRecord).where(AgentRunRecord.job_id == job["id"], AgentRunRecord.agent_type == "reviewer")) == 0
        assert db.scalar(select(func.count()).select_from(BrowserApplicationEventRecord).where(BrowserApplicationEventRecord.job_id == job["id"])) == 0


class FakeResponse:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self.data


def test_openai_uses_strict_schema_and_rejects_trailing_prose(monkeypatch):
    captured = {}

    def post(*args, **kwargs):
        captured.update(kwargs["json"])
        return FakeResponse({
            "status": "completed",
            "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps(VALID) + " prose"}]}],
            "usage": {},
        })

    monkeypatch.setattr("app.services.llm_service.httpx.post", post)
    with pytest.raises(StructuredOutputError, match="MALFORMED_STRUCTURED_OUTPUT"):
        OpenAIProvider("gpt-5.6-sol", api_key="test").generate("system", "{}", ApplicationGenerationDraft, max_tokens=6000)
    fmt = captured["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True
    assert fmt["schema"]["additionalProperties"] is False


def test_openai_classifies_incomplete_max_tokens_as_truncated(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_service.httpx.post",
        lambda *args, **kwargs: FakeResponse({
            "status": "incomplete",
            "incomplete_details": {"reason": "max_output_tokens"},
            "output": [],
            "usage": {"output_tokens": 3000},
        }),
    )
    with pytest.raises(OutputTruncatedError, match="OUTPUT_TRUNCATED"):
        OpenAIProvider("gpt-5.6-sol", api_key="test").generate("system", "{}", ApplicationGenerationDraft, max_tokens=3000)
