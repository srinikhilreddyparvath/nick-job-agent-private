from playwright.sync_api import sync_playwright
with sync_playwright() as runtime:
    browser=runtime.chromium.launch(headless=True)
    page=browser.new_page()
    page.set_content("<form><label>Email<input id='email' required></label><button type='submit'>Submit</button></form>")
    print({"chromium":browser.version,"fields":page.locator("input").count(),"submit_controls":page.locator("button[type=submit]").count()})
    browser.close()
