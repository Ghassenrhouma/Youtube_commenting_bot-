import os
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))


def login():
    account = input("Which account? (1 or 2): ").strip()
    if account not in ("1", "2"):
        print("Invalid choice. Enter 1 or 2.")
        return

    profile_path = f"profiles/account{account}"
    os.makedirs(profile_path, exist_ok=True)

    print(f"Opening browser for account {account}...")
    print("Log in to YouTube, then press Enter here when done.")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_path,
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ],
        )
        page = context.new_page()
        page.goto("https://www.youtube.com")
        input(">> Press Enter once you are logged in...")
        context.close()

    print(f"✓ Profile saved to '{profile_path}'")


if __name__ == "__main__":
    login()
