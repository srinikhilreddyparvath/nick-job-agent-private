"""Rendered RoleCall release sanity check; never follows external job links."""
from __future__ import annotations

import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = os.getenv("ROLECALL_URL", "http://localhost:3000")
SCREENSHOT_DIR = Path(os.getenv("ROLECALL_SCREENSHOT_DIR", "../docs/screenshots"))
ROUTES = ("/", "/onboarding", "/dashboard", "/saved", "/market", "/profile", "/settings")
VIEWPORTS = {"mobile": (375, 812), "tablet": (768, 1024), "desktop": (1440, 900)}


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    findings = []
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for label, (width, height) in VIEWPORTS.items():
        page = browser.new_page(viewport={"width": width, "height": height}, reduced_motion="reduce")
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(type(error).__name__))
        for route in ROUTES:
            response = page.goto(f"{BASE}{route}", wait_until="networkidle")
            page.locator("body").wait_for()
            slug = route.strip("/").replace("/", "-") or "landing"
            overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
            overflow_elements = page.evaluate("""() => [...document.querySelectorAll('body *')]
              .filter(e => { const r=e.getBoundingClientRect(); return r.right > innerWidth + 1 || r.left < -1; })
              .slice(0, 8).map(e => `${e.tagName.toLowerCase()}.${e.className || ''}`)""") if overflow else []
            h1_count = page.locator("h1").count()
            unlabeled_buttons = page.locator("button:not([aria-label])").evaluate_all(
                "els => els.filter(e => !(e.textContent || '').trim() && !e.getAttribute('title')).length"
            )
            findings.append({
                "viewport": label,
                "route": route,
                "http_ok": bool(response and response.ok),
                "rolecall_title": "RoleCall" in page.title(),
                "horizontal_overflow": overflow,
                "overflow_elements": overflow_elements,
                "h1_count": h1_count,
                "unlabeled_icon_buttons": unlabeled_buttons,
            })
            if label == "desktop" and route in {"/", "/dashboard", "/saved", "/market", "/profile"}:
                page.screenshot(path=str(SCREENSHOT_DIR / f"rolecall-{slug}.png"), full_page=True)
        findings[-1]["page_errors"] = list(errors)
        page.close()
    browser.close()
    passed = all(
        item["http_ok"] and item["rolecall_title"] and not item["horizontal_overflow"]
        and item["h1_count"] == 1 and item["unlabeled_icon_buttons"] == 0
        and not item.get("page_errors")
        for item in findings
    )
    print(json.dumps({"passed": passed, "checks": findings}, sort_keys=True))
