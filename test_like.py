"""Test autostart, ad handling, mid-roll ad detection, and liking."""
import time
import random
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright
from browser_helper import get_browser_context, patch_page
from comment_poster import (
    _ensure_video_playing, _is_ad_showing, _handle_ads,
    _watch_with_ad_checks, _try_like_video, _get_video_duration, _cap_watch_time,
)

load_dotenv()

VIDEO_ID = input("Enter a YouTube video ID (press Enter for default): ").strip()
if not VIDEO_ID:
    VIDEO_ID = "dQw4w9WgXcQ"

print(f"\n{'='*50}")
print(f"  Test: autostart + ads + like")
print(f"  Video: https://www.youtube.com/watch?v={VIDEO_ID}")
print(f"{'='*50}\n")

with sync_playwright() as p:
    context = get_browser_context(p)
    page = context.new_page()
    patch_page(page)

    # ── Step 1: Navigate ──────────────────────────────────────────────────────
    print("[1/4] Navigating to video...")
    page.goto(f"https://www.youtube.com/watch?v={VIDEO_ID}")
    page.wait_for_load_state("networkidle")
    print("  Page loaded.")

    # ── Step 2: Autostart + ad handling ──────────────────────────────────────
    print("\n[2/4] Starting video (handling ads if any)...")
    ad_before = _is_ad_showing(page)
    print(f"  Ad showing on load: {ad_before}")

    _ensure_video_playing(page)

    ad_after = _is_ad_showing(page)
    print(f"  Ad showing after handling: {ad_after}")

    is_playing = page.evaluate("() => { const v = document.querySelector('video'); return v && !v.paused; }")
    print(f"  Video playing: {is_playing}")

    if not is_playing:
        print("  ✗ WARNING: Video did not start — autostart may be blocked")
    else:
        print("  ✓ Autostart confirmed")

    # ── Step 3: Watch with mid-roll ad checks ────────────────────────────────
    print("\n[3/4] Watching 30s with mid-roll ad checks (8s chunks)...")
    duration = _get_video_duration(page)
    watch_time = _cap_watch_time(30, duration)
    print(f"  Video duration: {duration}s | Watch time: {int(watch_time)}s")

    _watch_with_ad_checks(page, watch_time)
    print("  ✓ Watch complete")

    # ── Step 4: Like ─────────────────────────────────────────────────────────
    print("\n[4/4] Attempting to like the video...")
    _try_like_video(page)

    # Final state check
    print("\n── Final state ──────────────────────────────────────────────────")
    is_still_playing = page.evaluate("() => { const v = document.querySelector('video'); return v && !v.paused; }")
    print(f"  Video still playing: {is_still_playing}")

    like_btn = page.query_selector("#segmented-like-button button")
    if like_btn:
        print(f"  Like button aria-pressed: {like_btn.get_attribute('aria-pressed')}")

    input("\nVerify in your bot account then press Enter to close...")
    context.close()

print("\n=== Test complete ===")
