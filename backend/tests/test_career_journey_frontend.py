import os

import pytest
from playwright.sync_api import sync_playwright


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FRONTEND_E2E") != "1",
    reason="set RUN_FRONTEND_E2E=1 to exercise the running frontend",
)


def test_find_jobs_progress_dashboard_and_mobile_navigation():
    queued={"id":901,"status":"queued","stage":"queued","source_count":1,"jobs_found":0,"unique_jobs":0,"promising_jobs":0,"semantic_selected":0,"semantic_completed":0,"semantic_failed":0,"ranked_jobs":0,"provider":None,"model":None,"estimated_cost":0,"message":"Waiting for the local worker","errors":[],"started_at":None,"completed_at":None}
    complete={**queued,"status":"completed","stage":"completed","jobs_found":12,"unique_jobs":9,"promising_jobs":5,"semantic_selected":3,"semantic_completed":3,"ranked_jobs":9,"provider":"mock","model":"mock-fit","estimated_cost":0.03,"message":"Jobs worth your attention are ready"}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        for viewport in ({"width":1440,"height":900},{"width":390,"height":844}):
            page=browser.new_page(viewport=viewport);errors=[];posts=[]
            page.on("console",lambda message:errors.append(message.text) if message.type=="error" else None)
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.route("http://localhost:8000/career-intelligence/find-jobs",lambda route:(posts.append(route.request.url),route.fulfill(status=202,json=queued)))
            page.route("http://localhost:8000/career-intelligence/runs/901",lambda route:route.fulfill(json=complete))
            page.goto("http://localhost:3000/dashboard",wait_until="networkidle")
            button=page.get_by_role("button",name="FIND JOBS")
            assert button.is_visible() and button.is_enabled()
            button.click();page.get_by_text("Jobs worth your attention are ready").wait_for(timeout=7000)
            assert page.get_by_text("3 / 3").is_visible()
            page.wait_for_load_state("networkidle")
            page.get_by_role("link",name="View analysis").first.click()
            page.wait_for_url("**/jobs/*")
            page.locator(".panel-label",has_text="WHY YOU MATCH").wait_for()
            assert page.locator(".panel-label",has_text="CONSTRAINTS").is_visible()
            assert page.locator(".panel-label",has_text="EXPERIMENTAL APPLICATION AUTOMATION").is_visible()
            assert page.get_by_text("Technical details").is_visible()
            assert len(posts)==1 and not errors
            page.close()
        browser.close()
