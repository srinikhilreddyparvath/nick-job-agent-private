import os

import pytest
from playwright.sync_api import sync_playwright

from app.models.profile import CandidateProfile, EvidenceRecord, JobPreferences, ProfileItem


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FRONTEND_E2E") != "1",
    reason="set RUN_FRONTEND_E2E=1 to exercise the running frontend",
)


def test_resume_review_and_approval_browser_flow(tmp_path):
    profile = CandidateProfile(
        professional_summary=ProfileItem(value="Engineer building reliable search systems.", evidence_ids=["DRAFT"]),
        experience=[ProfileItem(value="Machine Learning Engineer at Northstar Labs", evidence_ids=["DRAFT"])],
        skills=[ProfileItem(value="Python", evidence_ids=["DRAFT"])],
        education=[ProfileItem(value="M.S. Computer Science", evidence_ids=["DRAFT"])],
    )
    evidence = EvidenceRecord(
        id="DRAFT",
        category="experience",
        sub_category="role",
        statement="Machine Learning Engineer at Northstar Labs",
        source="resume",
        source_reference="resume.txt: Experience",
        verified=False,
        confidence=0.9,
        source_type="RESUME",
        source_document="resume.txt",
        source_section="Experience",
        supporting_text="Machine Learning Engineer at Northstar Labs",
    )
    preferences = JobPreferences()
    empty_state = {
        "profile": CandidateProfile().model_dump(mode="json"),
        "evidence": [],
        "preferences": preferences.model_dump(mode="json"),
        "configured": False,
    }
    approved_state = {
        "profile": profile.model_dump(mode="json"),
        "evidence": [{**evidence.model_dump(mode="json"), "verified": True}],
        "preferences": preferences.model_dump(mode="json"),
        "configured": True,
    }
    ingestion = {
        "metadata": {
            "document_id": "fixture-document",
            "filename": "fictional-resume.txt",
            "file_type": "txt",
            "text_length": 88,
            "page_count": None,
            "extraction_status": "EXTRACTED",
        },
        "draft": {
            "profile": profile.model_dump(mode="json"),
            "evidence": [evidence.model_dump(mode="json")],
            "warnings": [],
        },
        "provider": "mock",
        "model": "mock-structured-output",
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost": 0,
    }
    fixture = tmp_path / "fictional-resume.txt"
    fixture.write_text("Alex Morgan\nMachine Learning Engineer at Northstar Labs\nBuilt search evaluation tooling.", encoding="utf-8")
    requests = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        errors = []
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("pageerror", lambda error: errors.append(str(error)))

        def api(route):
            request = route.request
            requests.append((request.method, request.url))
            if request.method == "GET":
                route.fulfill(json=empty_state)
            elif request.method == "POST":
                route.fulfill(json=ingestion)
            else:
                route.fulfill(json=approved_state)

        page.route("http://localhost:8000/onboarding**", api)
        page.goto("http://localhost:3000/onboarding", wait_until="networkidle")
        assert page.get_by_role("heading", name="Teach the agent what matters to you.").is_visible()
        page.locator('input[type="file"]').set_input_files(str(fixture))
        page.get_by_text("Resume ready for review", exact=False).wait_for()
        assert page.get_by_text("EXTRACTED FROM RESUME").first.is_visible()
        page.get_by_role("textbox", name="SKILLS 1", exact=True).fill("Python and SQL")
        assert page.get_by_text("USER ADDED / EDITED").first.is_visible()
        page.get_by_role("checkbox", name="I reviewed target roles and constraints").check()
        page.get_by_role("button", name="APPROVE PROFILE & PREFERENCES").click()
        page.get_by_text("Approved. Your local profile", exact=False).wait_for()
        assert sum(method == "POST" for method, _ in requests) == 1
        assert sum(method == "PUT" for method, _ in requests) == 1
        assert not errors
        browser.close()


def test_resume_retry_uses_saved_upload(tmp_path):
    empty={"profile":CandidateProfile().model_dump(mode="json"),"evidence":[],"preferences":JobPreferences().model_dump(mode="json"),"configured":False}
    profile=CandidateProfile(skills=[ProfileItem(value="Python",evidence_ids=[])])
    success={"metadata":{"document_id":"stored-document","filename":"fictional-resume.txt","file_type":"txt","text_length":70,"page_count":None,"extraction_status":"EXTRACTED"},"draft":{"profile":profile.model_dump(mode="json"),"evidence":[],"warnings":[]},"provider":"mock","model":"mock","input_tokens":10,"output_tokens":10,"estimated_cost":0}
    fixture=tmp_path/"fictional-resume.txt";fixture.write_text("Alex Morgan\nMachine Learning Engineer\nBuilt reliable retrieval systems.",encoding="utf-8")
    uploads=[];retries=[]
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True);page=browser.new_page();errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.route("http://localhost:8000/onboarding",lambda route:route.fulfill(json=empty))
        page.route("http://localhost:8000/onboarding/resume",lambda route:(uploads.append(1),route.fulfill(status=503,json={"detail":{"code":"AI_REQUEST_TIMED_OUT","message":"Your resume was saved, but resume extraction timed out. Try extraction again."}})))
        page.route("http://localhost:8000/onboarding/resume/retry",lambda route:(retries.append(1),route.fulfill(json=success)))
        page.goto("http://localhost:3000/onboarding",wait_until="networkidle");page.locator('input[type="file"]').set_input_files(str(fixture))
        page.get_by_role("button",name="RETRY EXTRACTION").wait_for();page.get_by_role("button",name="RETRY EXTRACTION").click();page.get_by_text("Resume ready for review",exact=False).wait_for()
        assert uploads==[1] and retries==[1] and not errors
        browser.close()
