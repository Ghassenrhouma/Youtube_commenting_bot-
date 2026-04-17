import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def verify_cookies() -> bool:
    profile_path = os.getenv("PROFILE_PATH", "profiles/default")
    if not os.path.exists(profile_path):
        print(f"✗ Profile not found at '{profile_path}' — run login.py first")
        return False

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = context.new_page()
            page.goto("https://www.youtube.com")
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass
            if page.query_selector("#avatar-btn"):
                print("✓ Profile valid — logged in")
                return True
            else:
                print(f"✗ Not logged in — run login.py for profile '{profile_path}'")
                return False
        finally:
            context.close()


if __name__ == "__main__":
    verify_cookies()
