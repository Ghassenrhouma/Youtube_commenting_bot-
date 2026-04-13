import os
import random
import time
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

from browser_helper import (
    get_browser_context, patch_page,
    human_click, human_click_element, human_scroll, human_type,
)

load_dotenv()


def _wait_for_load(page, timeout=10000):
    """Wait for networkidle with a hard timeout — YouTube never fully idles."""
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except PlaywrightTimeoutError:
        pass  # page is loaded enough


DRY_RUN = os.getenv("DRY_RUN", "True").lower() == "true"
SKIP_DELAYS = os.getenv("SKIP_DELAYS", "True").lower() == "true"


def _random_imperfection(page):
    """Simulates human mistakes and corrections."""
    action = random.choice([
        "misclick_back", "reload", "pause_and_scroll",
        "nothing", "nothing", "nothing",
    ])

    if action == "misclick_back":
        try:
            page.go_back()
            time.sleep(random.uniform(1, 3))
            page.go_forward()
            time.sleep(random.uniform(1, 2))
            print("  [HUMAN] Simulated back/forward navigation")
        except Exception:
            pass

    elif action == "reload":
        try:
            page.reload()
            _wait_for_load(page)
            time.sleep(random.uniform(2, 4))
            print("  [HUMAN] Simulated page reload")
        except Exception:
            pass

    elif action == "pause_and_scroll":
        page.evaluate(f"window.scrollBy(0, {random.randint(-100, 300)})")
        time.sleep(random.uniform(2, 6))


def _search_and_click_video(page, video_id, video_title=""):
    """Types a search query and clicks the target video."""
    try:
        human_click(page, "input#search")
        time.sleep(random.uniform(0.5, 1.5))

        # Use title if available — humans never search by URL
        if video_title:
            # Occasionally shorten the query like a real user would
            words = video_title.split()
            if len(words) > 5 and random.random() < 0.4:
                query = " ".join(words[:random.randint(3, 5)])
            else:
                query = video_title
        else:
            query = video_id

        for char in query:
            page.keyboard.type(char)
            time.sleep(random.uniform(0.05, 0.15))

        time.sleep(random.uniform(0.5, 1.2))
        page.keyboard.press("Enter")
        _wait_for_load(page)
        time.sleep(random.uniform(2, 4))

        video_link = page.query_selector(f"a[href*='{video_id}']")
        if video_link:
            human_click_element(page, video_link)
            _wait_for_load(page)
        else:
            page.goto(f"https://www.youtube.com/watch?v={video_id}")
            _wait_for_load(page)

    except Exception:
        page.goto(f"https://www.youtube.com/watch?v={video_id}")
        _wait_for_load(page)


def _navigate_to_video(page, video_id, video_title=""):
    """Simulates a human arriving at a video naturally."""
    page.goto("https://www.youtube.com")
    _wait_for_load(page)
    time.sleep(random.uniform(3, 8))

    page.evaluate(f"window.scrollBy(0, {random.randint(200, 500)})")
    time.sleep(random.uniform(2, 5))

    if random.random() < 0.3:
        page.evaluate("window.scrollBy(0, -200)")
        time.sleep(random.uniform(1, 3))

    if random.random() < 0.5:
        _search_and_click_video(page, video_id, video_title)
    else:
        page.goto(f"https://www.youtube.com/watch?v={video_id}")
        _wait_for_load(page)

    if random.random() < 0.25:
        _random_imperfection(page)


def _is_ad_showing(page) -> bool:
    # .ad-showing on the player itself is the only reliable indicator
    # .ytp-ad-player-overlay exists in the DOM even during normal playback
    return page.evaluate("""
        () => !!document.querySelector('.html5-video-player.ad-showing')
    """)


def _handle_ads(page):
    """Wait for ads to finish. Only click skip when the button is clearly visible."""
    print("  [AD] Ad detected — waiting...")
    for _ in range(30):  # poll every 2s, up to 60s total
        if not _is_ad_showing(page):
            print("  [AD] Ad finished")
            return
        # Only click skip if the button is visible — don't touch anything else
        for selector in [".ytp-skip-ad-button", ".ytp-ad-skip-button-modern"]:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    print("  [AD] Skipping ad...")
                    human_click_element(page, btn)
                    time.sleep(random.uniform(1.5, 2.5))
                    break
            except Exception:
                pass
        time.sleep(2)


def _ensure_video_playing(page):
    """Wait for the player to load and handle any pre-roll ads. Let YouTube autoplay."""
    try:
        page.wait_for_selector(".html5-video-player", timeout=8000)
        time.sleep(random.uniform(1.5, 2.5))
        _handle_ads(page)
    except Exception:
        pass


def _is_player_error(page) -> bool:
    return page.evaluate("""
        () => {
            const err = document.querySelector('.ytp-error');
            if (!err) return false;
            const style = window.getComputedStyle(err);
            if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
            const rect = err.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            // Must have visible error text to avoid false positives
            const msg = err.querySelector('.ytp-error-content');
            return !!msg && (msg.innerText || '').trim().length > 0;
        }
    """)


def _recover_player_error(page, video_url: str):
    """Recover from a player error by clicking the in-player retry button."""
    print("  [ERROR] Player error — clicking retry button...")
    try:
        # Try clicking the retry button — avoid <a> tags (those are "Learn more" links)
        retried = False

        # 1. Any <button> inside the error overlay
        for btn in (page.query_selector_all(".ytp-error button") or []):
            if btn.is_visible():
                human_click_element(page, btn)
                retried = True
                break

        # 2. The error content area itself is clickable for retry
        if not retried:
            el = page.query_selector(".ytp-error-content-wrap")
            if el and el.is_visible():
                human_click_element(page, el)
                retried = True

        # 3. JS: find any element inside .ytp-error whose text says retry/reload (not a link)
        if not retried:
            page.evaluate("""
                () => {
                    const err = document.querySelector('.ytp-error');
                    if (!err) return;
                    const walker = document.createTreeWalker(err, NodeFilter.SHOW_ELEMENT);
                    while (walker.nextNode()) {
                        const n = walker.currentNode;
                        if (n.tagName === 'A') continue;
                        const t = (n.innerText || '').toLowerCase();
                        if (t.includes('retry') || t.includes('reload') || t.includes('tap to')) {
                            n.click(); break;
                        }
                    }
                }
            """)
            retried = True

        if retried:
            time.sleep(random.uniform(3.0, 5.0))
            if not _is_player_error(page):
                print("  [ERROR] ✓ Retry worked")
                _ensure_video_playing(page)
                return
    except Exception:
        pass

    # Retry button didn't clear it — fall back to page reload
    print("  [ERROR] Retry button failed — reloading page...")
    page.reload()
    _wait_for_load(page)
    time.sleep(random.uniform(4.0, 7.0))
    _ensure_video_playing(page)


def _watch_with_ad_checks(page, watch_time: float):
    """Just sleep for the watch duration — no polling, no interaction."""
    time.sleep(watch_time)


def _try_like_video(page):
    """Like the video if not already liked. Tries multiple selectors."""
    try:
        like_btn = None
        for selector in [
            "#segmented-like-button button",
            "ytd-like-button-renderer button",
            "like-button-view-model button",
            "button[aria-label*='like' i]",
            "button[aria-label*='aime' i]",
        ]:
            el = page.query_selector(selector)
            if el:
                like_btn = el
                break

        if not like_btn:
            print("  [LIKE] Button not found")
            return

        # Skip if already liked
        aria_pressed = like_btn.get_attribute("aria-pressed")
        if aria_pressed == "true":
            print("  [LIKE] Already liked — skipping")
            return

        # Scroll into view
        page.evaluate("el => el.scrollIntoView({behavior: 'smooth', block: 'center'})",
                      like_btn)
        time.sleep(random.uniform(0.6, 1.2))

        # Check bounding box — fallback to JS click if off-screen
        bbox = like_btn.bounding_box()
        if bbox:
            human_click_element(page, like_btn)
        else:
            page.evaluate("el => el.click()", like_btn)

        time.sleep(random.uniform(1.0, 2.0))
        aria_after = like_btn.get_attribute("aria-pressed")
        if aria_after == "true":
            print("  [LIKE] ✓ Liked")
        else:
            print("  [LIKE] Click sent but state unchanged — may not have registered")
    except Exception as e:
        print(f"  [LIKE] Failed: {e}")


def _get_video_duration(page) -> int:
    """Read video duration from the YouTube player. Returns seconds, or 600 as fallback."""
    try:
        duration_el = page.query_selector(".ytp-time-duration")
        if duration_el:
            text = (duration_el.inner_text() or "").strip()  # e.g. "12:34" or "1:02:34"
            parts = text.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 600  # safe fallback if element not found


def _cap_watch_time(desired: float, duration: int) -> float:
    """Ensure watch time is at most 85% of video duration, minimum 60s.
    Respects WATCH_MAX env var if set — picks randomly up to the cap."""
    max_watch = max(60, int(duration * 0.85))
    result = min(desired, max_watch)
    watch_max_env = int(os.getenv("WATCH_MAX", "0"))
    if watch_max_env and result > watch_max_env:
        result = random.uniform(max(30, watch_max_env * 0.5), watch_max_env)
    return result


def _variable_video_behavior(page):
    """Simulates different ways humans interact with a video before commenting."""
    _ensure_video_playing(page)
    duration = _get_video_duration(page)

    behavior = random.choices(
        ["quick_commenter", "normal_watcher", "engaged_watcher", "skeptical_browser"],
        weights=[20, 40, 25, 15],
    )[0]

    if behavior == "quick_commenter":
        watch_time = _cap_watch_time(random.uniform(180, 300), duration)
        print(f"  [HUMAN] Quick commenter — watching {int(watch_time)}s / {duration}s")
        _watch_with_ad_checks(page, watch_time)
        if random.random() < 0.20:
            _try_like_video(page)
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(random.uniform(1, 2))

    elif behavior == "normal_watcher":
        watch_time = _cap_watch_time(random.uniform(180, 360), duration)
        print(f"  [HUMAN] Normal watcher — watching {int(watch_time)}s / {duration}s")
        _watch_with_ad_checks(page, watch_time)
        if random.random() < 0.20:
            _try_like_video(page)
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(random.uniform(2, 4))
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(random.uniform(1, 3))

    elif behavior == "engaged_watcher":
        watch_time = _cap_watch_time(random.uniform(300, 600), duration)
        print(f"  [HUMAN] Engaged watcher — watching {int(watch_time)}s / {duration}s")
        _watch_with_ad_checks(page, watch_time)
        if random.random() < 0.20:
            _try_like_video(page)
        try:
            human_click(page, "tp-yt-paper-button#expand")
            time.sleep(random.uniform(2, 5))
        except Exception:
            pass
        page.evaluate("window.scrollBy(0, 400)")
        time.sleep(random.uniform(2, 4))

    elif behavior == "skeptical_browser":
        watch_time = _cap_watch_time(random.uniform(180, 360), duration)
        print(f"  [HUMAN] Skeptical browser — watching {int(watch_time)}s / {duration}s")
        _watch_with_ad_checks(page, watch_time)
        if random.random() < 0.20:
            _try_like_video(page)
        page.evaluate("window.scrollBy(0, 500)")
        time.sleep(random.uniform(2, 4))
        page.evaluate("window.scrollBy(0, -200)")
        time.sleep(random.uniform(1, 3))
        page.evaluate("window.scrollBy(0, 300)")
        time.sleep(random.uniform(1, 2))


def _type_reply(page, text):
    """Human-paced typing for reply boxes (element already focused)."""
    words = text.split(" ")
    total_words = len(words)

    for word_idx, word in enumerate(words):
        for char in word:
            page.keyboard.type(char)
            # Slower base: gauss centred at 0.13s
            delay = max(0.04, min(0.40, random.gauss(0.13, 0.05)))
            if char in ".,!?;:":
                # Re-reads after punctuation
                delay += random.uniform(0.20, 0.55)
            # Occasional typo: wrong char then backspace
            if char.isalpha() and random.random() < 0.025:
                time.sleep(delay)
                page.keyboard.type(random.choice("abcdefghijklmnopqrstuvwxyz"))
                time.sleep(random.uniform(0.15, 0.40))
                page.keyboard.press("Backspace")
                time.sleep(random.uniform(0.08, 0.22))
                page.keyboard.type(char)
                delay = random.uniform(0.06, 0.18)
            time.sleep(delay)

        if word_idx < total_words - 1:
            page.keyboard.type(" ")
            roll = random.random()
            if roll < 0.10:
                # "Thinking" pause — writer stops to consider next word
                time.sleep(random.uniform(1.0, 2.2))
            elif roll < 0.25:
                # Short hesitation
                time.sleep(random.uniform(0.35, 0.80))
            else:
                time.sleep(random.uniform(0.05, 0.18))

        # Mid-sentence thinking stop every ~8-14 words
        if word_idx > 0 and word_idx % random.randint(8, 14) == 0:
            time.sleep(random.uniform(1.2, 2.5))


def passive_browse_session(page=None):
    """Simulates a human casually browsing YouTube between comment sessions."""
    if DRY_RUN:
        print("  [HUMAN] DRY RUN: Would browse YouTube passively")
        return

    def _browse(pg):
        pg.goto("https://www.youtube.com")
        _wait_for_load(pg)
        time.sleep(random.uniform(3, 7))

        for _ in range(random.randint(2, 4)):
            pg.evaluate(f"window.scrollBy(0, {random.randint(200, 400)})")
            time.sleep(random.uniform(1.5, 4.0))

        video_links = pg.query_selector_all("ytd-rich-item-renderer a#video-title-link")
        if video_links:
            random_video = random.choice(video_links[:8])
            human_click_element(pg, random_video)
            _wait_for_load(pg)

            _ensure_video_playing(pg)
            watch_time = random.uniform(30, 90)
            print(f"  [HUMAN] Passively watching random video for {int(watch_time)}s")
            _watch_with_ad_checks(pg, watch_time)

            pg.evaluate("window.scrollBy(0, 300)")
            time.sleep(random.uniform(2, 5))

            if random.random() < 0.2:
                pg.go_back()
                time.sleep(random.uniform(2, 4))
                video_links2 = pg.query_selector_all("ytd-rich-item-renderer a#video-title-link")
                if video_links2:
                    choice = random.choice(video_links2[:8])
                    human_click_element(pg, choice)
                    _wait_for_load(pg)
                    _ensure_video_playing(pg)
                    _watch_with_ad_checks(pg, random.uniform(20, 60))

    if page is not None:
        _browse(page)
        return

    with sync_playwright() as p:
        context = get_browser_context(p)
        pg = context.new_page()
        patch_page(pg)
        try:
            _browse(pg)
        finally:
            context.close()


def post_comment(video_id: str, comment_text: str, page=None, video_title: str = "") -> str:
    if DRY_RUN:
        print(f"[DRY RUN] Would post comment on {video_id}:")
        print(f"  '{comment_text}'")
        return "dry_run_comment_id"

    def _execute(pg):
        _navigate_to_video(pg, video_id, video_title)
        _variable_video_behavior(pg)

        if f"watch?v={video_id}" not in pg.url:
            print(f"  [WARN] Autoplay navigated away — returning to target video")
            pg.goto(f"https://www.youtube.com/watch?v={video_id}")
            _wait_for_load(pg)
            time.sleep(random.uniform(2, 4))

        human_scroll(pg)

        try:
            pg.wait_for_selector("#simplebox-placeholder", timeout=15000)
        except PlaywrightTimeoutError:
            raise Exception("Comment box not found — cookies may be expired")

        # Scroll placeholder into view before clicking
        placeholder = pg.query_selector("#simplebox-placeholder")
        if placeholder:
            placeholder.scroll_into_view_if_needed()
            time.sleep(random.uniform(0.5, 1.0))

        human_click(pg, "#simplebox-placeholder")
        time.sleep(random.uniform(0.8, 1.5))

        # If the box didn't expand, try clicking again or use JS focus
        if not pg.query_selector("#contenteditable-root"):
            time.sleep(random.uniform(0.5, 1.0))
            try:
                pg.click("#simplebox-placeholder")
            except Exception:
                pass
            time.sleep(random.uniform(0.5, 1.0))

        if not pg.query_selector("#contenteditable-root"):
            pg.evaluate("document.querySelector('#simplebox-placeholder')?.click()")
            time.sleep(random.uniform(0.5, 1.0))

        try:
            pg.wait_for_selector("#contenteditable-root", timeout=10000)
        except PlaywrightTimeoutError:
            raise Exception("Comment input did not open — YouTube may have blocked the interaction")

        time.sleep(random.uniform(1.0, 2.5))

        human_type(pg, "#contenteditable-root", comment_text)
        time.sleep(random.uniform(1.5, 3.0))

        submit_btn = pg.query_selector("ytd-commentbox #submit-button")
        if not submit_btn:
            submit_btn = pg.query_selector("#submit-button")
        human_click_element(pg, submit_btn)
        time.sleep(random.uniform(3.0, 5.0))

        return f"posted_{video_id}"

    if page is not None:
        return _execute(page)

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            pg = context.new_page()
            patch_page(pg)
            return _execute(pg)
        finally:
            context.close()


def post_reply(video_id: str, parent_comment_id: str, reply_text: str, comment_text: str = "") -> str:
    if DRY_RUN:
        print(f"[DRY RUN] Would reply to comment on {video_id}:")
        print(f"  '{reply_text}'")
        return "dry_run_reply_id"

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            page = context.new_page()
            patch_page(page)
            _navigate_to_video(page, video_id)
            _variable_video_behavior(page)
            human_scroll(page)

            page.wait_for_selector("ytd-comment-thread-renderer", timeout=15000)

            target_thread = None
            comment_snippet = comment_text[:60].strip() if comment_text else ""
            print(f"  [REPLY] Looking for comment: '{comment_snippet[:80]}'")

            for scroll_attempt in range(12):
                threads = page.query_selector_all("ytd-comment-thread-renderer")
                for thread in threads:
                    text_el = thread.query_selector("#content-text")
                    thread_text = (text_el.inner_text() or "").strip() if text_el else ""
                    if comment_snippet and comment_snippet in thread_text:
                        print(f"  [REPLY] Matched on scroll attempt {scroll_attempt}: '{thread_text[:80]}'")
                        target_thread = thread
                        break
                if target_thread:
                    break
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(random.uniform(1.0, 2.0))

            if not target_thread:
                print(f"  [REPLY] ✗ Target comment not found after 12 scrolls — aborting")
                raise Exception("Target comment not found in page — not posting to avoid misfire")

            target_thread.scroll_into_view_if_needed()
            time.sleep(random.uniform(0.5, 1.0))

            reply_btn = target_thread.query_selector("#reply-button-end")
            if not reply_btn:
                raise Exception("Reply button not found on target comment")
            human_click_element(page, reply_btn)
            time.sleep(random.uniform(1.0, 2.0))

            input_el = target_thread.query_selector("#contenteditable-root")
            if not input_el:
                target_thread.wait_for_selector("#contenteditable-root", timeout=8000)
                input_el = target_thread.query_selector("#contenteditable-root")

            human_click_element(page, input_el)
            time.sleep(random.uniform(0.5, 1.0))

            _type_reply(page, reply_text)
            time.sleep(random.uniform(1.5, 3.0))

            submit_btn = target_thread.query_selector("#submit-button")
            if not submit_btn:
                raise Exception("Submit button not found in reply box")
            human_click_element(page, submit_btn)
            time.sleep(random.uniform(3.0, 5.0))

            return f"reply_{parent_comment_id}"
        finally:
            context.close()


def scrape_and_reply(video_id: str, video_title: str, is_replyable_fn, generate_reply_fn, page=None) -> dict:
    """
    Scrape comments and post a reply in a single browser session.
    Returns {"comment_text": ..., "reply_text": ..., "comment_id": ...}
    Raises Exception if no replyable comment is found or DRY_RUN is True.
    """
    if DRY_RUN:
        raise Exception("DRY_RUN=True — scrape_and_reply skipped")

    def _execute(pg):
        _navigate_to_video(pg, video_id, video_title)
        _variable_video_behavior(pg)

        if f"watch?v={video_id}" not in pg.url:
            print(f"  [WARN] Autoplay navigated away — returning to target video")
            pg.goto(f"https://www.youtube.com/watch?v={video_id}")
            _wait_for_load(pg)
            time.sleep(random.uniform(2, 4))

        human_scroll(pg)

        pg.wait_for_selector("ytd-comment-thread-renderer", timeout=15000)

        target_thread = None
        target_text = ""
        seen_threads = set()

        for scroll_attempt in range(15):
            threads = pg.query_selector_all("ytd-comment-thread-renderer")
            candidates = []
            for thread in threads:
                tid = id(thread)
                if tid in seen_threads:
                    continue
                seen_threads.add(tid)
                text_el = thread.query_selector("#content-text")
                text = (text_el.inner_text() or "").strip() if text_el else ""
                like_el = thread.query_selector("#vote-count-middle")
                like_text = (like_el.inner_text() or "").strip() if like_el else ""
                try:
                    likes = int(like_text.replace(",", "")) if like_text else 0
                except ValueError:
                    likes = 0
                if text and is_replyable_fn(text):
                    candidates.append((likes, text, thread))

            if candidates:
                candidates.sort(key=lambda x: x[0], reverse=True)
                _, target_text, target_thread = candidates[0]
                print(f"  [REPLY] Found replyable comment (scroll {scroll_attempt}): '{target_text[:80]}'")
                break

            pg.evaluate("window.scrollBy(0, 600)")
            time.sleep(random.uniform(1.0, 2.0))

        if not target_thread:
            raise Exception("No replyable comments found on this video")

        reply_text = generate_reply_fn(video_title, target_text)
        print(f"  [REPLY] Generated reply: '{reply_text[:100]}'")

        target_thread.scroll_into_view_if_needed()
        time.sleep(random.uniform(0.5, 1.0))

        reply_btn = target_thread.query_selector("#reply-button-end")
        if not reply_btn:
            raise Exception("Reply button not found on target comment")
        human_click_element(pg, reply_btn)
        time.sleep(random.uniform(1.0, 2.0))

        input_el = target_thread.query_selector("#contenteditable-root")
        if not input_el:
            target_thread.wait_for_selector("#contenteditable-root", timeout=8000)
            input_el = target_thread.query_selector("#contenteditable-root")

        human_click_element(pg, input_el)
        time.sleep(random.uniform(0.5, 1.0))

        _type_reply(pg, reply_text)
        time.sleep(random.uniform(1.5, 3.0))

        submit_btn = target_thread.query_selector("#submit-button")
        if not submit_btn:
            raise Exception("Submit button not found in reply box")
        human_click_element(pg, submit_btn)

        # Wait and verify the reply input cleared (confirms submission went through)
        time.sleep(random.uniform(5.0, 8.0))
        input_after = target_thread.query_selector("#contenteditable-root")
        if input_after:
            text_after = (input_after.inner_text() or "").strip()
            if text_after:
                raise Exception("Reply box still has content after submit — post may have failed")

        print(f"  [REPLY] ✓ Submission confirmed (input cleared)")

        return {
            "comment_text": target_text,
            "reply_text": reply_text,
            "comment_id": f"reply_{video_id}",
        }

    if page is not None:
        return _execute(page)

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            pg = context.new_page()
            patch_page(pg)
            return _execute(pg)
        finally:
            context.close()


def random_human_action(video_id: str, page=None):
    action = random.choice(["like", "scroll_only", "scroll_only", "nothing"])

    if DRY_RUN:
        print(f"[DRY RUN] Would perform action '{action}' on {video_id}")
        return

    if action == "nothing":
        return

    def _act(pg):
        pg.goto(f"https://www.youtube.com/watch?v={video_id}")
        _wait_for_load(pg)
        _ensure_video_playing(pg)
        time.sleep(random.uniform(20, 45))
        if action == "like":
            _try_like_video(pg)
        elif action == "scroll_only":
            human_scroll(pg)
            time.sleep(random.uniform(5, 15))

    if page is not None:
        _act(page)
        return

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            pg = context.new_page()
            patch_page(pg)
            _act(pg)
        finally:
            context.close()


def safe_delay(page=None):
    if SKIP_DELAYS:
        print("  [DELAY] Skipped (SKIP_DELAYS=True)")
        return

    # Allow per-account delay override via env vars (in seconds)
    delay_min = int(os.getenv("DELAY_MIN", "0"))
    delay_max = int(os.getenv("DELAY_MAX", "0"))

    if delay_min and delay_max:
        delay = random.uniform(delay_min, delay_max)
    else:
        hour = datetime.now().hour
        active = (9 <= hour < 12) or (14 <= hour < 18) or (20 <= hour < 22)
        # New account: minimum 10 min during active hours, 20 min off-peak
        delay = random.uniform(600, 1500) if active else random.uniform(1200, 2400)
        # 20% chance of a longer "got distracted" pause
        if random.random() < 0.20:
            extra = random.uniform(600, 1800)
            delay += extra

    if page is not None:
        # Split: 30-60% on the current video page, rest on YouTube home
        split = random.uniform(0.30, 0.60)
        on_video = delay * split
        on_home = delay - on_video
        print(f"  [DELAY] {delay:.0f}s split — {on_video:.0f}s on video page, {on_home:.0f}s on home")
        time.sleep(on_video)
        try:
            page.goto("https://www.youtube.com")
            _wait_for_load(page)
            # Idle on home page with occasional scrolls
            home_end = time.time() + on_home
            while time.time() < home_end:
                chunk = min(random.uniform(40, 120), home_end - time.time())
                if chunk > 0:
                    time.sleep(chunk)
                if time.time() < home_end:
                    page.evaluate(f"window.scrollBy(0, {random.randint(100, 400)})")
        except Exception:
            time.sleep(on_home)
    else:
        print(f"  [DELAY] Waiting {delay:.0f}s ({delay/60:.1f} min)...")
        time.sleep(delay)


if __name__ == "__main__":
    print(f"DRY_RUN={DRY_RUN} | SKIP_DELAYS={SKIP_DELAYS}")
    assert DRY_RUN is True, "Set DRY_RUN=True before testing!"

    print("\n--- Testing post_comment (dry run) ---")
    result = post_comment("test_video_id", "Test comment text.")
    print(f"Result: {result}")

    print("\n--- Testing post_reply (dry run) ---")
    result = post_reply("test_video_id", "test_comment_id", "Test reply.")
    print(f"Result: {result}")

    print("\n--- Testing random_human_action (dry run) ---")
    random_human_action("test_video_id")

    print("\n--- Testing passive_browse_session (dry run) ---")
    passive_browse_session()

    print("\n--- Testing safe_delay (should skip) ---")
    safe_delay()

    print("\n✓ All comment_poster tests passed")
