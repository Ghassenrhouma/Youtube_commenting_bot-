import os
from datetime import datetime
import gspread
from dotenv import load_dotenv

load_dotenv()

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
SERVICE_ACCOUNT_PATH = os.getenv("SERVICE_ACCOUNT_PATH", "service_account.json")


def get_commented_video_ids() -> set:
    """Fetch all video IDs already logged in the sheet to avoid re-commenting."""
    try:
        client = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
        sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
        rows = sheet.get_all_values()
        # Column index 3 = video_id (0-indexed), skip header row
        video_ids = {row[4] for row in rows[1:] if len(row) > 4 and row[4]}
        print(f"[TRACKER] Loaded {len(video_ids)} already-commented video IDs from sheet")
        if video_ids:
            print(f"[TRACKER] Sample IDs: {list(video_ids)[:5]}")
        return video_ids
    except Exception as e:
        print(f"[TRACKER] ERROR loading sheet history: {e}")
        print(f"[TRACKER] ⚠ Proceeding with empty history — duplicates may occur")
        return set()


def log_action(video_id, video_title, text, comment_id, status,
               action_type, source, dry_run=False, replied_to=""):
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    account = os.getenv("ACCOUNT_ID", "account1")

    if dry_run:
        print("[DRY RUN] Would log row:")
        print(f"  timestamp    : {timestamp}")
        print(f"  account      : {account}")
        print(f"  action_type  : {action_type}")
        print(f"  source       : {source}")
        print(f"  video_id     : {video_id}")
        print(f"  video_link   : https://www.youtube.com/watch?v={video_id}")
        print(f"  video_title  : {video_title}")
        print(f"  text         : {text}")
        print(f"  comment_id   : {comment_id}")
        print(f"  status       : {status}")
        print(f"  replied_to   : {replied_to or '(none)'}")
        print(f"  dry_run      : yes")
        return

    video_link = f"https://www.youtube.com/watch?v={video_id}"
    client = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
    sheet = client.open_by_key(GOOGLE_SHEET_ID).sheet1
    sheet.append_row([
        timestamp, account, action_type, source, video_id, video_link, video_title,
        text, comment_id, status, "no", replied_to,
    ])


if __name__ == "__main__":
    log_action(
        video_id="test123",
        video_title="Test Video",
        text="Test comment",
        comment_id="dry_run_id",
        status="posted",
        action_type="top-level comment",
        source="keyword_search",
        dry_run=True
    )
    print("✓ Tracker dry run passed")
