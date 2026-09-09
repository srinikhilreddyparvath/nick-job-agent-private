"""Non-submitting full browser acceptance journey with safe metadata output."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


BASE = os.getenv("ROLECALL_URL", "http://localhost:3000")
API = os.getenv("ROLECALL_API_URL", "http://localhost:8000")
RESUME = Path(os.environ["ROLECALL_ACCEPTANCE_RESUME"]).resolve()
TARGETS = os.environ["ROLECALL_ACCEPTANCE_TARGETS"]
DOMAINS = os.getenv("ROLECALL_ACCEPTANCE_DOMAINS", "")
LOCATIONS = os.getenv("ROLECALL_ACCEPTANCE_LOCATIONS", "Remote")
LABEL = os.getenv("ROLECALL_ACCEPTANCE_LABEL", "candidate")


def body(response):
    assert response.ok, f"HTTP {response.status}: {response.text()[:240]}"
    return response.json()


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(type(error).__name__))
    reset = page.request.post(f"{API}/operations/reset-local-state", data={"confirmation": "RESET ROLECALL"})
    body(reset)

    before_hash = hashlib.sha256(RESUME.read_bytes()).hexdigest()
    page.goto(f"{BASE}/onboarding", wait_until="networkidle")
    with page.expect_response(lambda response: response.url.endswith("/onboarding/resume"), timeout=180_000) as upload_info:
        page.locator('input[type="file"]').set_input_files(str(RESUME))
    upload_response = upload_info.value
    retry_used = False
    if not upload_response.ok:
        # A recoverable AI failure must preserve the stored document and expose
        # an idempotent retry path; exercise that path instead of re-uploading.
        page.get_by_role("button", name="RETRY EXTRACTION").wait_for(timeout=30_000)
        with page.expect_response(lambda response: response.url.endswith("/onboarding/resume/retry"), timeout=180_000) as retry_info:
            page.get_by_role("button", name="RETRY EXTRACTION").click()
        upload_response = retry_info.value
        retry_used = True
    upload = body(upload_response)
    page.get_by_text("Resume ready for review", exact=False).wait_for(timeout=30_000)
    draft = upload["draft"]
    profile = draft["profile"]
    metadata = upload["metadata"]

    summary = page.get_by_role("textbox", name="Professional summary")
    summary.fill(summary.input_value() + " Reviewed in release acceptance.")
    page.get_by_label("Target roles").fill(TARGETS)
    page.get_by_label("Domains / role families").fill(DOMAINS)
    page.get_by_label("Preferred locations").fill(LOCATIONS)
    page.get_by_role("checkbox", name="I reviewed target roles and constraints").check()
    page.get_by_role("button", name="APPROVE PROFILE & PREFERENCES").click()
    page.get_by_text("Approved. Your local profile", exact=False).wait_for(timeout=30_000)
    page.get_by_role("link", name="FIND JOBS").click()
    page.wait_for_url("**/dashboard")
    page.get_by_role("button", name="FIND JOBS").click()
    page.get_by_text("Jobs worth your attention are ready").wait_for(timeout=600_000)
    page.reload(wait_until="networkidle")
    cards = page.locator(".job-card")
    cards.first.wait_for(timeout=30_000)
    visible = cards.count()
    companies = set(cards.locator(".job-heading>span").all_text_contents())

    jobs = body(page.request.get(f"{API}/jobs?limit=10"))["items"]
    top = jobs[:10]
    urls_valid = all(urlparse(job["apply_url"]).scheme in {"http", "https"} and bool(urlparse(job["apply_url"]).netloc) for job in top)
    unique = len({(job["company"], job["title"], job["apply_url"]) for job in top}) == len(top)
    active = all(job.get("liveness_status") not in {"EXPIRED", "NOT_FOUND"} for job in top)
    complete = all(job.get("company") and job.get("title") for job in top)

    page.get_by_role("link", name="View analysis").first.click()
    page.wait_for_url("**/jobs/*")
    job_id = int(page.url.rstrip("/").split("/")[-1])
    for panel in ("WHY YOU MATCH", "REAL GAPS", "CONSTRAINTS", "POSTING CONFIDENCE", "PEOPLE CLOSE TO THIS ROLE"):
        page.get_by_text(panel, exact=True).wait_for()
    view_job = page.get_by_role("link", name="View Job")
    view_url = view_job.get_attribute("href") or ""
    view_valid = urlparse(view_url).scheme in {"http", "https"} and bool(urlparse(view_url).netloc)

    status_before_view = body(page.request.get(f"{API}/jobs/{job_id}")).get("application_status")
    with page.expect_popup(timeout=30_000) as popup_info:
        view_job.click()
    destination = popup_info.value
    destination.wait_for_load_state("domcontentloaded", timeout=60_000)
    external_navigation_performed = urlparse(destination.url).scheme in {"http", "https"}
    destination.close()
    status_after_view = body(page.request.get(f"{API}/jobs/{job_id}")).get("application_status")
    view_preserved_status = status_before_view == status_after_view

    page.get_by_role("button", name="SAVE", exact=True).click()
    page.get_by_text("Pipeline updated").wait_for()
    page.get_by_label("Pipeline status").select_option("applied")
    page.get_by_text("Pipeline updated").wait_for()
    page.get_by_label("Pipeline status").select_option("interview")
    page.get_by_text("Pipeline updated").wait_for()

    contact_button = page.get_by_role("button", name="Find people close to this role")
    if contact_button.count():
        contact_button.click()
        page.wait_for_timeout(12_000)
    contacts = body(page.request.get(f"{API}/jobs/{job_id}/contacts"))
    contact_ok = contacts.get("status") in {"COMPLETE", "EMPTY", "PARTIAL", "FAILED"}

    package_request = {
        "questions": [{"question_text": "Why are you interested in this role?", "required": True, "answer_length": "MEDIUM", "source": "manual"}],
        "force": False,
        "cover_letter_requested": False,
        "resume_pages": 2,
        "use_mock": True,
    }
    package = body(page.request.post(f"{API}/jobs/{job_id}/application-package", data=package_request))
    review = body(page.request.post(f"{API}/jobs/{job_id}/application-package/review?use_mock=true"))
    pkg = review.get("package") or package.get("package") or {}
    # Removed unsupported claims demonstrate that the gate worked. The retained
    # material must be traceable; rejected claims must never survive into it.
    retained_bullets = pkg.get("tailored_resume_preview", {}).get("bullets", [])
    fact_gate = all(
        item.get("source_evidence_ids")
        and item.get("validation_status") not in {"UNSUPPORTED", "REJECTED"}
        for item in retained_bullets
    )
    original_unchanged = before_hash == hashlib.sha256(RESUME.read_bytes()).hexdigest()

    assert not errors, errors
    print(json.dumps({
        "candidate": LABEL,
        "format": metadata["file_type"],
        "pages": metadata.get("page_count"),
        "characters": metadata["text_length"],
        "experiences": len(profile.get("experience", [])),
        "skills": len(profile.get("skills", [])),
        "education": len(profile.get("education", [])),
        "evidence": len(draft.get("evidence", [])),
        "visible_jobs": visible,
        "companies": len(companies),
        "top10_count": len(top),
        "top10_urls_valid": urls_valid,
        "top10_unique": unique,
        "top10_active": active,
        "top10_complete": complete,
        "saved_and_pipeline_interview": True,
        "contact_result": contacts.get("status"),
        "contact_safe": contact_ok,
        "application_package": package.get("status"),
        "fact_gate": fact_gate,
        "original_resume_unchanged": original_unchanged,
        "retry_used": retry_used,
        "view_job_valid": view_valid,
        "external_navigation_performed": external_navigation_performed,
        "view_job_preserved_status": view_preserved_status,
    }, sort_keys=True))
    browser.close()
