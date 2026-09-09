from pathlib import Path

import pytest
from pypdf import PdfReader

from app.agents.application import ApplicationAgent
from app.agents.browser import BrowserAgent
from app.agents.reviewer import ReviewerAgent
from app.db.database import SessionLocal
from app.db.models import ApplicationPackageRecord,ApprovedAnswerHistoryRecord
from app.models.application_package import ApplicationAnswer,ApplicationQuestionInput,PackageGenerateRequest,ResumeBullet,TailoredResumeData
from app.services.application_package_service import ApplicationPackageService
from app.services.llm_service import LLMService,MockLLMProvider
from app.services.policy_service import AnswerBankService,WorkAuthorizationService


QUESTIONS=[
 {"question_text":"Why are you interested in this role?","required":True,"answer_length":"MEDIUM"},
 {"question_text":"Will you now or in the future require employment visa sponsorship?","required":True,"answer_length":"SHORT"},
 {"question_text":"How many years of vector database experience do you have?","required":True,"answer_length":"SHORT"},
 {"question_text":"Middle Name","required":True,"answer_length":"SHORT"},
 {"question_text":"What is your current salary?","required":True,"answer_length":"SHORT"},
]


def prepared_job(client):
    job=client.post("/jobs/ingest-text",json={"source_url":"https://public.example/jobs/research","company":"Example Research Lab","title":"Research Engineer, Search","location":"San Francisco, CA","job_description_text":"Build search retrieval systems, evaluate ranking quality, write Python, and collaborate across engineering and research."}).json()["job"]
    assert client.post(f"/jobs/{job['id']}/analyze",json={"use_mock":True}).status_code==200
    assert client.post(f"/jobs/{job['id']}/research",json={"use_mock":True}).status_code==200
    return job


def test_agent_contracts_are_active_bounded_and_browser_activated_in_phase5():
    assert ApplicationAgent.definition.active and ReviewerAgent.definition.active
    assert "browser" not in " ".join(ApplicationAgent.definition.allowed_tools).lower()
    assert "submit" not in " ".join(ApplicationAgent.definition.allowed_actions).lower()
    assert BrowserAgent.definition.active is True
    assert "submit_application" in BrowserAgent.definition.allowed_tools


def test_question_policy_work_authorization_middle_name_years_and_salary():
    assert WorkAuthorizationService().assess("Will you now or in the future require employment visa sponsorship?").answer=="YES"
    service=ApplicationPackageService(LLMService(MockLLMProvider()))
    for index,text in enumerate(("Middle Name","How many years of experience do you have?","What is your salary history?"),1):
        answer=service._policy_answer(ApplicationQuestionInput(question_text=text),index)
        assert answer.requires_human_review and answer.answer is None


def test_fresh_user_answer_bank_starts_empty_instead_of_failing(tmp_path):
    bank=AnswerBankService(tmp_path/"answer_bank.local.json")
    assert set(bank.all())=={"approved_structured","evidence_generated","human_review_required"}


def test_package_persistence_strategy_provenance_answers_cache_and_pdf(client):
    job=prepared_job(client);request={"use_mock":True,"questions":QUESTIONS,"resume_pages":2}
    created=client.post(f"/jobs/{job['id']}/application-package",json=request)
    assert created.status_code==200,created.text
    body=created.json();assert body["status"]=="REVIEW_REQUIRED";package=body["package"]
    assert package["resume_strategy"]["target_role_family"]=="RESEARCH_AI"
    assert package["tailored_resume_preview"]["bullets"] and all(x["source_evidence_ids"] for x in package["tailored_resume_preview"]["bullets"])
    sponsorship=next(x for x in package["application_answers"] if "visa sponsorship" in x["question_text"]);assert sponsorship["answer"]=="YES" and sponsorship["answer_type"]=="APPROVED_STRUCTURED"
    sensitive=[x for x in package["application_answers"] if x["question_text"] in {"Middle Name","What is your current salary?"}];assert all(x["requires_human_review"] for x in sensitive)
    path=Path(package["tailored_resume_path"]);assert path.exists() and path.stat().st_size>0
    text="\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages);assert "Alex Morgan" in text and "Target: Research Engineer, Search at Example Research Lab" in text and "WALMART_" not in text
    cached=client.post(f"/jobs/{job['id']}/application-package",json=request).json();assert cached["status"]=="cached" and cached["package"]["id"]==package["id"]
    assert client.get(f"/jobs/{job['id']}/tailored-resume").status_code==404
    assert client.get(f"/jobs/{job['id']}/application-package/tailored-resume").status_code==200
    assert client.get(f"/jobs/{job['id']}/application-package/tailored-resume/download").headers["content-type"]=="application/pdf"


def test_reviewer_approval_edit_revalidation_and_answer_bank_learning(client):
    job=prepared_job(client);client.post(f"/jobs/{job['id']}/application-package",json={"use_mock":True,"questions":QUESTIONS})
    reviewed=client.post(f"/jobs/{job['id']}/application-package/review?use_mock=true").json();assert reviewed["status"]=="READY_FOR_REVIEW" and reviewed["package"]["review_status"]=="PASS"
    approved=client.post(f"/jobs/{job['id']}/application-package/approve",json={"save_reusable_answers":True});assert approved.status_code==200 and approved.json()["status"]=="APPROVED"
    with SessionLocal() as db:assert db.query(ApprovedAnswerHistoryRecord).count()>=1
    answer=reviewed["package"]["application_answers"][0];edited=client.patch(f"/jobs/{job['id']}/application-package/answers/{answer['id']}",json={"answer":"Invented quantum ownership"}).json();assert edited["status"]=="REVIEW_REQUIRED" and edited["approved_at"] is None
    failed=client.post(f"/jobs/{job['id']}/application-package/review?use_mock=true").json();assert failed["status"]=="REVIEW_REQUIRED" and failed["package"]["review_status"]=="FAIL",failed


def test_resume_bullet_and_answer_character_limit_models():
    bullet=ResumeBullet(id="b",section="experience",employer_or_context="Northstar",generated_text="Verified statement",source_evidence_ids=["EXPERIENCE_001"],source_resume_text="Verified statement",transformation_type="PARAPHRASED")
    assert bullet.source_evidence_ids==["EXPERIENCE_001"]
    with pytest.raises(ValueError):ApplicationAnswer(id="a",question_text="q",answer="1234",answer_type="EVIDENCE_GENERATED",character_limit=3)


def test_llm_disabled_generation_fails_closed_without_package(client):
    job=prepared_job(client);response=client.post(f"/jobs/{job['id']}/application-package",json={"questions":[]})
    assert response.status_code==200 and response.json()["status"]=="GENERATION_FAILED"
    with SessionLocal() as db:assert db.query(ApplicationPackageRecord).count()==0
