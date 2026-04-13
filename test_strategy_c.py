import os
from dotenv import load_dotenv
from video_finder import get_popular_videos_for_replies, _is_replyable
from comment_generator import generate_reply
from comment_poster import scrape_and_reply
from tracker import log_action, get_commented_video_ids

load_dotenv()
DRY_RUN = os.getenv("DRY_RUN", "True").lower() == "true"

print(f"=== Strategy C Reply Test | DRY_RUN={DRY_RUN} ===\n")

if DRY_RUN:
    print("DRY_RUN=True — scrape_and_reply requires a real browser session.")
    print("Set DRY_RUN=False in .env to test posting.\n")

seen_video_ids = get_commented_video_ids()
print("--- Step 1: Finding popular videos ---")
videos = get_popular_videos_for_replies(max_results=5, seen_ids=seen_video_ids)
print(f"Found {len(videos)} popular video(s)\n")

if not videos:
    print("✗ No popular videos found — check view count filter or keyword search")
    exit(1)

for video in videos:
    print(f"Video : {video['title'][:70]}")
    print(f"ID    : {video['video_id']}")
    print(f"Views : {video.get('view_count', '?')}\n")

    if DRY_RUN:
        print("--- [DRY RUN] Skipping browser session ---\n")
        break

    confirm = input("Scrape comments and post a reply on this video? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Skipped.")
        continue

    print("--- Opening browser, scraping and replying in one session ---")
    try:
        result = scrape_and_reply(
            video["video_id"], video["title"],
            is_replyable_fn=_is_replyable,
            generate_reply_fn=generate_reply,
        )
        log_action(
            video["video_id"], video["title"], result["reply_text"],
            result["comment_id"], "posted", "reply", "thread_reply",
            dry_run=False, replied_to=result["comment_text"],
        )
        print(f"\n✓ Posted and logged")
        print(f"  Replied to : {result['comment_text'][:100]}")
        print(f"  Reply      : {result['reply_text'][:100]}")
        break  # success — stop here
    except Exception as e:
        print(f"✗ Failed: {e} — trying next video...")

print("\n=== Test complete ===")
