import os
import random
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# Override COOKIES_PATH before browser_helper is imported so it picks up account 2's cookies
os.environ["PROFILE_PATH"] = os.getenv("ACCOUNT1_PROFILE", "profiles/account1")
os.environ["ACCOUNT_ID"] = "account1"
os.environ["DELAY_MIN"] = "450"   # 7.5 min between comments
os.environ["DELAY_MAX"] = "530"   # 8.8 min max
os.environ["WATCH_MAX"] = "150"   # cap video watching at 2.5 min per video

from playwright.sync_api import sync_playwright

from browser_helper import get_browser_context, patch_page
from video_finder import (
    get_videos_by_keyword, get_channel_recent_videos,
    get_video_comments, get_popular_videos_for_replies,
    _is_replyable, TARGET_CHANNELS, SEARCH_QUERIES,
)
from comment_generator import generate_comment, generate_reply
from comment_poster import post_comment, post_reply, scrape_and_reply, random_human_action, safe_delay, passive_browse_session
from tracker import log_action, get_commented_video_ids
from verify_cookies import verify_cookies

DRY_RUN = os.getenv("DRY_RUN", "True").lower() == "true"
COMMENT_LIMIT = int(os.getenv("ACCOUNT2_LIMIT", "10"))
SKIP_DELAYS = os.getenv("SKIP_DELAYS", "True").lower() == "true"
COOKIES_PATH = os.environ["COOKIES_PATH"]



def is_night_hours() -> bool:
    return 0 <= datetime.now().hour < 8


def sleep_until_8am():
    now = datetime.now()
    seconds = ((8 - now.hour) * 3600) - (now.minute * 60) - now.second
    print(f"[TIME GATE] 00:00-08:00 — sleeping {seconds // 3600}h {(seconds % 3600) // 60}m until 08:00...")
    time.sleep(max(seconds, 0))


SESSION_DEADLINE = 55 * 60  # hard cap: stop after 55 minutes


def run_session(seen_video_ids: set) -> dict:
    """Run one full comment session. Returns summary dict."""
    session_start = time.time()
    action_count = 0
    strategy_a = strategy_b = strategy_c = errors = 0
    next_passive_browse = random.randint(4, 7)

    def time_left() -> float:
        return SESSION_DEADLINE - (time.time() - session_start)

    def out_of_time() -> bool:
        remaining = time_left()
        if remaining <= 0:
            print(f"  [TIME] Session deadline reached — stopping early.")
        return remaining <= 0

    if COMMENT_LIMIT >= 3:
        remainder = COMMENT_LIMIT - 3
        extras = [0, 0, 0]
        for _ in range(remainder):
            extras[random.randint(0, 2)] += 1
        alloc_a = 1 + extras[0]
        alloc_b = 1 + extras[1]
        alloc_c = 1 + extras[2]
    else:
        alloc_a = alloc_b = alloc_c = 0
        for _ in range(COMMENT_LIMIT):
            pick = random.randint(0, 2)
            if pick == 0:
                alloc_a += 1
            elif pick == 1:
                alloc_b += 1
            else:
                alloc_c += 1
    limit_a = alloc_a
    limit_b = alloc_a + alloc_b
    print(f"  Strategy split: A={alloc_a} | B={alloc_b} | C={alloc_c}")

    shared_page = None
    shared_context = None
    _pw = None
    if not DRY_RUN:
        _pw = sync_playwright().start()
        shared_context = get_browser_context(_pw)
        shared_page = shared_context.new_page()
        patch_page(shared_page)
        print("  [BROWSER] Session opened")

    try:
        print("\n  [WARM-UP] Passive browse before commenting...")
        passive_browse_session(page=shared_page)

        print("\n  [SCRAPE] Finding videos...")

        targets_a = []
        if alloc_a > 0:
            for query in SEARCH_QUERIES:
                if len(targets_a) >= alloc_a:
                    break
                for video in get_videos_by_keyword(query, max_results=5, page=shared_page):
                    if video["video_id"] not in seen_video_ids and len(targets_a) < alloc_a:
                        targets_a.append((video, "keyword_search"))
        else:
            print("  [SKIP] Strategy A — 0 slots")

        targets_b = []
        if alloc_b > 0:
            for channel in TARGET_CHANNELS:
                if len(targets_b) >= alloc_b:
                    break
                for video in get_channel_recent_videos(channel["url"], channel["name"], max_results=3, page=shared_page):
                    if video["video_id"] not in seen_video_ids and len(targets_b) < alloc_b:
                        targets_b.append((video, channel["name"]))
        else:
            print("  [SKIP] Strategy B — 0 slots")

        targets_c = []
        if alloc_c > 0:
            for video in get_popular_videos_for_replies(max_results=alloc_c + 3, seen_ids=seen_video_ids, page=shared_page):
                if len(targets_c) < alloc_c:
                    targets_c.append(video)
        else:
            print("  [SKIP] Strategy C — 0 slots")

        prepared_a = []
        if targets_a:
            print("  [AI] Generating comments for A...")
            for video, source in targets_a:
                try:
                    comment = generate_comment(video["title"], video.get("description", ""))
                    prepared_a.append((video, source, comment))
                except Exception as e:
                    print(f"✗ Generation failed: {e}")

        prepared_b = []
        if targets_b:
            print("  [AI] Generating comments for B...")
            for video, source in targets_b:
                try:
                    comment = generate_comment(video["title"], video.get("description", ""))
                    prepared_b.append((video, source, comment))
                except Exception as e:
                    print(f"✗ Generation failed: {e}")

        print(f"  Ready: A={len(prepared_a)} B={len(prepared_b)} C={len(targets_c)}")

        if prepared_a:
            print("\n===== STRATEGY A: Keyword Search =====")
        for video, source, comment in prepared_a:
            if action_count >= limit_a or out_of_time():
                break
            seen_video_ids.add(video["video_id"])
            try:
                comment_id = post_comment(video["video_id"], comment, page=shared_page, video_title=video["title"])
                log_action(video["video_id"], video["title"], comment, comment_id, "posted", "top-level comment", source, dry_run=DRY_RUN)
                action_count += 1
                strategy_a += 1
                print(f"✓ [A {action_count}/{COMMENT_LIMIT}] {video['title'][:50]} ({int(time_left()//60)}m left)")
                if not SKIP_DELAYS and action_count % random.randint(3, 5) == 0:
                    random_human_action(video["video_id"], page=shared_page)
                if action_count < COMMENT_LIMIT and not out_of_time():
                    safe_delay(page=shared_page)
                if action_count >= next_passive_browse and not SKIP_DELAYS and not out_of_time():
                    passive_browse_session(page=shared_page)
                    next_passive_browse = action_count + random.randint(4, 7)
                    safe_delay(page=shared_page)
            except Exception as e:
                errors += 1
                log_action(video["video_id"], video["title"], "", "", f"error: {str(e)[:80]}", "top-level comment", source, dry_run=DRY_RUN)
                print(f"✗ Error on {video['video_id']}: {str(e)[:80]}")

        if prepared_b:
            print("\n===== STRATEGY B: Channel Monitoring =====")
        for video, source, comment in prepared_b:
            if action_count >= limit_b or out_of_time():
                break
            seen_video_ids.add(video["video_id"])
            try:
                comment_id = post_comment(video["video_id"], comment, page=shared_page, video_title=video["title"])
                log_action(video["video_id"], video["title"], comment, comment_id, "posted", "top-level comment", source, dry_run=DRY_RUN)
                action_count += 1
                strategy_b += 1
                print(f"✓ [B {action_count}/{COMMENT_LIMIT}] [{source}] {video['title'][:40]} ({int(time_left()//60)}m left)")
                if not SKIP_DELAYS and action_count % random.randint(3, 5) == 0:
                    random_human_action(video["video_id"], page=shared_page)
                if action_count < COMMENT_LIMIT and not out_of_time():
                    safe_delay(page=shared_page)
                if action_count >= next_passive_browse and not SKIP_DELAYS and not out_of_time():
                    passive_browse_session(page=shared_page)
                    next_passive_browse = action_count + random.randint(4, 7)
                    safe_delay(page=shared_page)
            except Exception as e:
                errors += 1
                log_action(video["video_id"], video["title"], "", "", f"error: {str(e)[:80]}", "top-level comment", source, dry_run=DRY_RUN)
                print(f"✗ Error: {str(e)[:80]}")

        if targets_c:
            print("\n===== STRATEGY C: Thread Replies =====")
        for video in targets_c:
            if action_count >= COMMENT_LIMIT or out_of_time():
                break
            try:
                result = scrape_and_reply(
                    video["video_id"], video["title"],
                    is_replyable_fn=_is_replyable,
                    generate_reply_fn=generate_reply,
                    page=shared_page,
                )
                log_action(video["video_id"], video["title"], result["reply_text"], result["comment_id"], "posted", "reply", "thread_reply", dry_run=DRY_RUN, replied_to=result["comment_text"])
                seen_video_ids.add(video["video_id"])
                action_count += 1
                strategy_c += 1
                print(f"✓ [C {action_count}/{COMMENT_LIMIT}] {video['title'][:40]} ({int(time_left()//60)}m left)")
                if action_count < COMMENT_LIMIT and not out_of_time():
                    safe_delay(page=shared_page)
                if action_count >= next_passive_browse and not SKIP_DELAYS and not out_of_time():
                    passive_browse_session(page=shared_page)
                    next_passive_browse = action_count + random.randint(4, 7)
                    safe_delay(page=shared_page)
            except Exception as e:
                errors += 1
                print(f"✗ Reply error: {str(e)[:80]}")

    finally:
        if shared_context is not None:
            shared_context.close()
        if _pw is not None:
            _pw.stop()
        if not DRY_RUN:
            print("  [BROWSER] Session closed")

    return {"actions": action_count, "a": strategy_a, "b": strategy_b, "c": strategy_c, "errors": errors}


def main():
    mode_label = "DRY RUN" if DRY_RUN else "PRODUCTION"
    delays_label = "SKIPPED" if SKIP_DELAYS else "ACTIVE"
    print("================================")
    print("  DocShipper YouTube Bot — Account 2")
    print(f"  Mode: {mode_label}")
    print(f"  Comments per session: {COMMENT_LIMIT}")
    print(f"  Cookies: {COOKIES_PATH}")
    print(f"  Delays: {delays_label}")
    print("  Press Ctrl+C to stop")
    print("================================")


    if not verify_cookies():
        exit(1)

    seen_video_ids = get_commented_video_ids()
    session_count = 0
    total_actions = 0

    try:
        while True:
            if not SKIP_DELAYS and is_night_hours():
                sleep_until_8am()
                continue

            session_count += 1
            print(f"\n{'='*40}")
            print(f"  SESSION {session_count} — {datetime.now().strftime('%H:%M:%S')}")
            print(f"{'='*40}")

            result = run_session(seen_video_ids)
            total_actions += result["actions"]

            print(f"\n  Session {session_count} done: {result['actions']} comments | "
                  f"A={result['a']} B={result['b']} C={result['c']} errors={result['errors']}")
            print(f"  Total so far: {total_actions} comments")

            if not SKIP_DELAYS:
                gap = random.randint(300, 420)
                print(f"\n[LOOP] Next session in {gap // 60}m {gap % 60}s...")
                time.sleep(gap)

    except KeyboardInterrupt:
        print(f"\n\nBot stopped. {session_count} sessions completed, {total_actions} total comments.")


if __name__ == "__main__":
    main()
