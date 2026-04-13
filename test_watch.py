"""
Test video watching in isolation.
Navigates to a video, watches it for 90 seconds, and reports whether
"Something went wrong" appears — without running any commenting logic.

Usage:
    python test_watch.py
    python test_watch.py https://www.youtube.com/watch?v=VIDEO_ID
"""

import sys
import time
from playwright.sync_api import sync_playwright
from browser_helper import get_browser_context, patch_page

VIDEO_URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=jNQXAC9IVRw"
WATCH_SECONDS = 90


def is_player_error(page) -> bool:
    return page.evaluate("""
        () => {
            const err = document.querySelector('.ytp-error');
            if (!err) return false;
            const style = window.getComputedStyle(err);
            if (style.display === 'none' || style.visibility === 'hidden') return false;
            const rect = err.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            const msg = err.querySelector('.ytp-error-content');
            return !!msg && (msg.innerText || '').trim().length > 0;
        }
    """)


def is_ad_showing(page) -> bool:
    return page.evaluate("() => !!document.querySelector('.html5-video-player.ad-showing')")


def get_playback_time(page) -> float:
    return page.evaluate("""
        () => {
            const v = document.querySelector('video');
            return v ? v.currentTime : 0;
        }
    """)


def main():
    print(f"[TEST] Opening: {VIDEO_URL}")
    print(f"[TEST] Will watch for {WATCH_SECONDS}s and report errors\n")

    _pw = sync_playwright().start()
    context = get_browser_context(_pw)
    page = context.new_page()
    patch_page(page)

    try:
        page.goto(VIDEO_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(3)

        print("[TEST] Page loaded. Starting watch loop (checking every 5s)...\n")

        start = time.time()
        while time.time() - start < WATCH_SECONDS:
            elapsed = time.time() - start
            playback = get_playback_time(page)
            ad = is_ad_showing(page)
            err = is_player_error(page)

            status = f"[{elapsed:5.1f}s] playback={playback:.1f}s"
            if ad:
                status += "  [AD PLAYING]"
            if err:
                status += "  *** PLAYER ERROR DETECTED ***"

            print(status)

            if err:
                print("\n[TEST] ERROR appeared at wall-clock elapsed:", round(elapsed, 1), "s")
                print("[TEST] Video had played to:", round(playback, 1), "s")
                print("[TEST] Waiting 10s to see if it clears on its own...")
                time.sleep(10)
                if is_player_error(page):
                    print("[TEST] Error PERSISTS after 10s")
                else:
                    print("[TEST] Error cleared on its own")
                break

            time.sleep(5)
        else:
            print(f"\n[TEST] Watched {WATCH_SECONDS}s with NO errors. Player is stable.")

    finally:
        context.close()
        _pw.stop()


if __name__ == "__main__":
    main()
