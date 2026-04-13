import json
import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()

def verify_cookies() -> bool:
    cookies_path = os.getenv("COOKIES_PATH", "youtube_cookies.json")
    with open(cookies_path) as f:
        cookies = json.load(f)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        try:
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto("https://www.youtube.com")
            page.wait_for_load_state("networkidle")

            if page.query_selector("#avatar-btn"):
                print("✓ Cookies valid — logged in")
                return True
            else:
                print("✗ Cookies expired — re-run save_cookies.py")
                return False
        finally:
            browser.close()

if __name__ == "__main__":
    result = verify_cookies()
    print(result)
