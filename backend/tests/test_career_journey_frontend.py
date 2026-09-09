import os

import pytest
from playwright.sync_api import sync_playwright


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_FRONTEND_E2E") != "1",
    reason="set RUN_FRONTEND_E2E=1 to exercise the running frontend",
)


def test_find_jobs_progress_dashboard_and_mobile_navigation():
    queued={"id":901,"status":"queued","stage":"queued","source_count":4,"sources_scanned":0,"sources_succeeded":0,"sources_failed":0,"companies_represented":0,"jobs_found":0,"unique_jobs":0,"promising_jobs":0,"semantic_selected":0,"semantic_completed":0,"semantic_failed":0,"ranked_jobs":0,"provider":None,"model":None,"estimated_cost":0,"message":"Waiting for the local worker","errors":[],"started_at":None,"completed_at":None}
    complete={**queued,"status":"completed","stage":"completed","sources_scanned":4,"sources_succeeded":3,"sources_failed":1,"companies_represented":3,"jobs_found":12,"unique_jobs":9,"promising_jobs":5,"semantic_selected":3,"semantic_completed":3,"ranked_jobs":9,"provider":"mock","model":"mock-fit","estimated_cost":0.03,"message":"Jobs worth your attention are ready"}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        for viewport in ({"width":1440,"height":900},{"width":390,"height":844}):
            page=browser.new_page(viewport=viewport);errors=[];posts=[];contact_posts=[]
            page.on("console",lambda message:errors.append(message.text) if message.type=="error" else None)
            page.on("pageerror",lambda error:errors.append(str(error)))
            page.route("http://localhost:8000/career-intelligence/find-jobs",lambda route:(posts.append(route.request.url),route.fulfill(status=202,json=queued)))
            page.route("http://localhost:8000/career-intelligence/runs/901",lambda route:route.fulfill(json=complete))
            contact_result={"items":[{"contact_id":71,"job_id":1,"name":"Fictional Peer","current_title":"Staff Research Engineer, Search Ranking","company":"Example Company","public_profile_url":"https://example.com/team/peer","source_type":"COMPANY_TEAM_PAGE","source_url":"https://example.com/team","team":"search ranking","domains":["search","ranking"],"location":None,"recruiting_relevance":False,"direct_function_ownership":False,"company_is_small":False,"relationship_status":"VERIFIED","relationship_confidence":.88,"evidence":[],"role_similarity":95,"team_similarity":100,"domain_similarity":100,"company_match":True,"seniority_usefulness":90,"location_relevance":0,"relevance_score":92,"relevance_reason":"Public evidence supports a closely related role connection.","discovered_at":"2026-09-06T00:00:00Z","last_checked_at":"2026-09-06T00:00:00Z"}],"status":"COMPLETE","message":None,"sources_checked":1,"pages_checked":3,"candidates_discovered":4,"cached":False}
            page.route("**/jobs/*/contacts/discover*",lambda route:(contact_posts.append(route.request.url),route.fulfill(json=contact_result)))
            page.goto("http://localhost:3000/dashboard",wait_until="networkidle")
            button=page.get_by_role("button",name="FIND JOBS")
            assert button.is_visible() and button.is_enabled()
            button.click();page.get_by_text("Jobs worth your attention are ready").wait_for(timeout=7000)
            page.wait_for_load_state("networkidle")
            page.get_by_role("link",name="View analysis").first.click()
            page.wait_for_url("**/jobs/*")
            page.locator(".panel-label",has_text="WHY YOU MATCH").wait_for()
            assert page.locator(".panel-label",has_text="CONSTRAINTS").is_visible()
            assert page.get_by_text("Experimental application automation",exact=True).is_visible()
            assert page.get_by_text("Ranking signal, not a hiring prediction",exact=True).is_visible()
            view_job=page.get_by_role("link",name="View Job")
            assert view_job.is_visible() and view_job.get_attribute("target")=="_blank"
            assert view_job.get_attribute("href").startswith("http")
            assert page.locator(".panel-label",has_text="PEOPLE CLOSE TO THIS ROLE").is_visible()
            assert page.get_by_text("No sufficiently relevant public contacts found yet.").is_visible()
            # A prior live acceptance run may leave a truthful cached empty
            # result, in which case the action is labelled "Refresh people".
            people_panel=page.locator("section.panel",has_text="PEOPLE CLOSE TO THIS ROLE")
            people_panel.locator(".card-actions button").first.click()
            page.get_by_text("Staff Research Engineer, Search Ranking").wait_for()
            assert page.get_by_text("Hiring relationship is not assumed.").is_visible()
            assert page.get_by_text("Technical details",exact=True).is_visible()
            assert len(posts)==1 and len(contact_posts)==1 and not errors
            page.close()
        browser.close()


def test_find_jobs_stops_after_repeated_progress_connection_failures():
    queued={"id":902,"status":"queued","stage":"queued","source_count":20,"sources_scanned":0,"sources_succeeded":0,"sources_failed":0,"companies_represented":0,"jobs_found":0,"unique_jobs":0,"promising_jobs":0,"semantic_selected":0,"semantic_completed":0,"semantic_failed":0,"ranked_jobs":0,"provider":None,"model":None,"estimated_cost":0,"message":"Waiting for the local worker","errors":[],"started_at":None,"completed_at":None}
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1280,"height":800})
        page.route("http://localhost:8000/career-intelligence/find-jobs",lambda route:route.fulfill(status=202,json=queued))
        page.route("http://localhost:8000/career-intelligence/runs/902",lambda route:route.abort())
        page.goto("http://localhost:3000/dashboard",wait_until="networkidle")
        button=page.get_by_role("button",name="FIND JOBS")
        if button.is_enabled():
            button.click()
        page.get_by_text("RoleCall could not confirm that discovery is still running.").wait_for(timeout=25000)
        assert page.get_by_role("button",name="REFRESH STATUS").is_visible()
        assert page.get_by_role("button",name="FIND JOBS").is_enabled()
        browser.close()
