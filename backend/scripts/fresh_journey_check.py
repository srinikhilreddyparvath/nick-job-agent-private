"""Non-submitting browser smoke test for an isolated fictional local state."""
from pathlib import Path
from playwright.sync_api import sync_playwright


ROOT=Path(__file__).resolve().parents[2]
RESUME=ROOT/"backend"/"tests"/"fixtures"/"fictional_resume.txt"


with sync_playwright() as playwright:
    browser=playwright.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1440,"height":900})
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.goto("http://localhost:3000/onboarding",wait_until="networkidle")
    page.locator('input[type="file"]').set_input_files(str(RESUME))
    page.get_by_text("Resume ready for review",exact=False).wait_for(timeout=30000)
    summary=page.get_by_role("textbox",name="Professional summary")
    summary.fill(summary.input_value()+" Reviewed by the user.")
    page.get_by_label("Target roles").fill("Machine Learning Engineer, Search Engineer")
    page.get_by_label("Domains / role families").fill("search, ranking, machine learning")
    page.get_by_label("Preferred locations").fill("San Francisco, Remote")
    page.get_by_role("checkbox", name="I reviewed target roles and constraints").check()
    page.get_by_role("button",name="APPROVE PROFILE & PREFERENCES").click()
    page.get_by_text("Approved. Your local profile",exact=False).wait_for(timeout=15000)
    page.get_by_role("link",name="FIND JOBS").click();page.wait_for_url("**/dashboard")
    button=page.get_by_role("button",name="FIND JOBS")
    assert button.is_enabled(),"Find Jobs must work without manual sources"
    button.click();page.get_by_text("Jobs worth your attention are ready").wait_for(timeout=420000)
    page.reload(wait_until="networkidle")
    cards=page.locator(".job-card");cards.first.wait_for(timeout=30000)
    companies=set(cards.locator(".job-heading>span").all_text_contents());visible_count=cards.count()
    assert len(companies)>=2,"Diversified results should include multiple companies when qualifying jobs exist"
    page.get_by_role("link",name="View analysis").first.click();page.wait_for_url("**/jobs/*")
    for label in ("WHY YOU MATCH","REAL GAPS","CONSTRAINTS","PEOPLE CLOSE TO THIS ROLE"):
        assert page.locator(".panel-label",has_text=label).is_visible()
    assert page.get_by_text("Experimental application automation",exact=True).is_visible()
    assert not errors,errors
    print("FRESH_JOURNEY_OK",len(companies),visible_count)
    browser.close()
