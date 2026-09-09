"""Verify View Job reaches the external destination without changing pipeline state."""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


BASE = os.getenv("ROLECALL_URL", "http://localhost:3000")
API = os.getenv("ROLECALL_API_URL", "http://localhost:8000")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(f"{BASE}/dashboard", wait_until="networkidle")
    page.get_by_role("link", name="View analysis").first.click()
    page.wait_for_url("**/jobs/*")
    job_id = int(page.url.rstrip("/").split("/")[-1])
    before = page.request.get(f"{API}/jobs/{job_id}").json().get("application_status")
    with page.expect_popup(timeout=30_000) as popup_info:
        page.get_by_role("link", name="View Job").click()
    destination = popup_info.value
    destination.wait_for_load_state("domcontentloaded", timeout=60_000)
    after = page.request.get(f"{API}/jobs/{job_id}").json().get("application_status")
    result = {
        "external_destination": urlparse(destination.url).scheme in {"http", "https"},
        "pipeline_status_unchanged": before == after,
        "final_submit_clicks": 0,
    }
    destination.close()
    browser.close()
    print(json.dumps(result, sort_keys=True))
