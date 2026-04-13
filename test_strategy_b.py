"""Test Strategy B (channel monitoring + comment) in isolation."""
import os
from dotenv import load_dotenv
from video_finder import get_channel_recent_videos, TARGET_CHANNELS
from comment_generator import generate_comment
from comment_poster import post_comment
from tracker import log_action, get_commented_video_ids

load_dotenv()
DRY_RUN = os.getenv("DRY_RUN", "True").lower() == "true"

print(f"=== Strategy B Test | DRY_RUN={DRY_RUN} ===\n")

seen_video_ids = get_commented_video_ids()
channel = TARGET_CHANNELS[0]

print(f"Channel: {channel['name']} ({channel['url']})")
videos = get_channel_recent_videos(channel["url"], channel["name"], max_results=5)
print(f"Found {len(videos)} recent video(s)\n")

target = None
for v in videos:
    if v["video_id"] not in seen_video_ids:
        target = v
        break

if not target:
    print("✗ No unseen videos found")
else:
    print(f"Video : {target['title'][:70]}")
    print(f"ID    : {target['video_id']}")
    print(f"Upload: {target.get('upload_time', '?')}\n")

    comment = generate_comment(target["title"], target.get("description", ""))
    print(f"Generated comment:\n  {comment}\n")

    if not DRY_RUN:
        confirm = input("Post this comment? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Skipped.")
        else:
            comment_id = post_comment(target["video_id"], comment, video_title=target["title"])
            log_action(target["video_id"], target["title"], comment,
                       comment_id, "posted", "top-level comment", channel["name"], dry_run=False)
            print(f"✓ Posted — id: {comment_id}")
    else:
        result = post_comment(target["video_id"], comment, video_title=target["title"])
        log_action(target["video_id"], target["title"], comment,
                   result, "posted", "top-level comment", channel["name"], dry_run=True)
        print(f"✓ Dry run complete — result: {result}")

print("\n=== Test complete ===")
