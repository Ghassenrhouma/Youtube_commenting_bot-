import os
import time
import random
import re
from urllib.parse import quote_plus
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from browser_helper import get_browser_context, patch_page, human_scroll

load_dotenv()

TARGET_CHANNELS = [
    {"name": "EcomCrew",         "url": "https://www.youtube.com/@EcomCrew/videos"},
    {"name": "Jungle Scout",     "url": "https://www.youtube.com/@JungleScout/videos"},
    {"name": "MyWifeQuitHerJob", "url": "https://www.youtube.com/@mywifequitherjob/videos"},
    {"name": "Freightos",        "url": "https://www.youtube.com/@Freightos/videos"},
    {"name": "SupplyChainBrain", "url": "https://www.youtube.com/@SupplyChainBrain/videos"},
    {"name": "My Amazon Guy",    "url": "https://www.youtube.com/@myamazonguy/videos"},
    {"name": "Helium 10",        "url": "https://www.youtube.com/@Helium10/videos"},
    {"name": "Dan Vas",          "url": "https://www.youtube.com/@DanVas/videos"},
    {"name": "Wholesale Ted",    "url": "https://www.youtube.com/@WholesaleTed/videos"},
    {"name": "Full-Time FBA",    "url": "https://www.youtube.com/@FullTimeFBA/videos"},
]

SEARCH_QUERIES = [
    # Import / freight intent
    "import from China",
    "freight forwarder",
    "customs clearance",
    "shipping from China to Europe",
    "import duties explained",
    "sourcing from Alibaba",

    # Pain points (high engagement)
    "import problems",
    "customs delay",
    "shipping costs too high",
    "supplier scam China",
    "how to find suppliers China",

    # SME / e-commerce angle
    "dropshipping from China",
    "Amazon FBA sourcing",
    "e-commerce logistics",
    "product sourcing tips",

    # French market
    "importer depuis la Chine",
    "transitaire international",
    "dédouanement France",
    "sourcing Asie",
]


def _parse_view_count(text: str) -> int:
    """Parse '10K views', '1.2M vues', '5,3 K vues' etc. into an integer."""
    text = text.strip().upper().replace("\u00a0", " ")
    # Replace French decimal comma (e.g. "5,3") with dot before stripping commas
    text = re.sub(r"(\d),(\d)", r"\1.\2", text)
    text = text.replace(",", "")
    match = re.search(r"([\d.]+)\s*([KMB]?)\s*(VIEW|VUE)", text)
    if not match:
        match = re.search(r"([\d.]+)\s*([KMB]?)", text)
    if not match:
        return 0
    num = float(match.group(1))
    suffix = match.group(2)
    multipliers = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
    return int(num * multipliers.get(suffix, 1))


def _is_recent(upload_time: str) -> bool:
    """Return True if video was uploaded within ~3 months.
    Handles both English and French time strings."""
    if not upload_time or upload_time.lower() == "unknown":
        return True  # benefit of the doubt

    t = upload_time.lower().strip()

    # Detect years — English: "1 year ago" / French: "il y a 1 an", "2 ans"
    if re.search(r"\d+\s*(year|years|ans?\b)", t):
        return False

    # Detect months — exclude if more than 3
    month_match = re.search(r"(\d+)\s*(month|months|mois)", t)
    if month_match:
        return int(month_match.group(1)) <= 3

    # Everything else (hours, days, weeks, minutes) is recent enough
    return True


def _is_english_title(title: str) -> bool:
    """Returns False if title contains non-Latin scripts or looks like Arabic transliteration."""
    if re.search(r"[\u0600-\u06FF]", title):  # Arabic script
        return False
    if re.search(r"[\u4e00-\u9fff]", title):  # Chinese script
        return False
    # Catch Arabic transliteration in Latin: digits mixed into words e.g. "9BAL", "DHO7K", "E5ER"
    if len(re.findall(r"\b[A-Z]*\d[A-Z]+\b|\b[A-Z]+\d[A-Z]*\b", title)) >= 2:
        return False
    return True



def _human_search(page, query: str):
    """Types query into YouTube search bar like a real human."""
    page.goto("https://www.youtube.com/?hl=en&gl=US")
    page.wait_for_load_state("networkidle")
    time.sleep(random.uniform(2, 5))

    # Try multiple search bar selectors
    search_selector = None
    for sel in ["input#search", "input[name='search_query']", "#search-input input", "ytd-searchbox input"]:
        try:
            page.wait_for_selector(sel, timeout=5000)
            search_selector = sel
            break
        except Exception:
            continue

    if not search_selector:
        # Fallback: navigate directly to search results
        page.goto(f"https://www.youtube.com/results?search_query={quote_plus(query)}&hl=en&gl=US")
        page.wait_for_load_state("networkidle")
        time.sleep(random.uniform(2, 4))
        return

    page.click(search_selector)
    time.sleep(random.uniform(0.8, 2.0))

    for char in query:
        page.keyboard.type(char)
        time.sleep(random.uniform(0.05, 0.18))
        if random.random() < 0.05:
            time.sleep(random.uniform(0.5, 1.5))

    time.sleep(random.uniform(0.5, 1.5))
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle")
    time.sleep(random.uniform(2, 4))


def get_videos_by_keyword(query: str, max_results: int = 5, page=None) -> list:
    def _scrape(pg):
        results = []
        _human_search(pg, query)
        human_scroll(pg)

        renderers = pg.query_selector_all("ytd-video-renderer")
        for renderer in renderers[:15]:
            if len(results) >= max_results:
                break

            title_el = renderer.query_selector("#video-title")
            if not title_el:
                continue

            href = title_el.get_attribute("href") or ""
            match = re.search(r"v=([a-zA-Z0-9_-]+)", href)
            if not match:
                continue
            video_id = match.group(1)

            title = (title_el.inner_text() or "").strip()

            channel_el = renderer.query_selector("ytd-channel-name")
            channel = (channel_el.inner_text() if channel_el else "").strip()

            desc_el = renderer.query_selector("#description-text")
            description = (desc_el.inner_text() if desc_el else "").strip()

            meta_spans = renderer.query_selector_all("#metadata-line span")
            view_text = meta_spans[0].inner_text().strip() if len(meta_spans) > 0 else ""
            upload_time = meta_spans[1].inner_text().strip() if len(meta_spans) > 1 else ""

            if not _is_english_title(title):
                continue

            if upload_time and re.search(r"\d+\s*(year|years|ans?\b)", upload_time.lower()):
                continue

            results.append({
                "video_id": video_id,
                "title": title,
                "description": description,
                "channel": channel,
                "upload_time": upload_time,
                "view_count_text": view_text,
            })
        return results

    if page is not None:
        return _scrape(page)

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            pg = context.new_page()
            patch_page(pg)
            return _scrape(pg)
        finally:
            context.close()


def get_channel_recent_videos(channel_url: str, channel_name: str,
                               max_results: int = 3, page=None) -> list:
    def _scrape(pg):
        results = []
        pg.goto(channel_url)
        pg.wait_for_load_state("networkidle")
        time.sleep(3)
        for _ in range(3):
            pg.evaluate("window.scrollBy(0, 1000)")
            time.sleep(1.5)
        human_scroll(pg)

        elements = pg.query_selector_all("ytd-rich-item-renderer")
        print(f"  [DEBUG] Found {len(elements)} raw video elements on {channel_name} page")

        for element in elements[:20]:
            if len(results) >= max_results:
                break
            try:
                link = element.query_selector("a#video-title-link, a#thumbnail")
                if not link:
                    continue

                href = link.get_attribute("href")
                if not href or "watch?v=" not in href:
                    continue

                video_id = href.split("v=")[1].split("&")[0]

                title_el = element.query_selector(
                    "#video-title, yt-formatted-string#video-title"
                )
                title = title_el.inner_text().strip() if title_el else "Unknown"

                upload_time = "unknown"
                for span in element.query_selector_all("#metadata-line span"):
                    span_text = span.inner_text().strip()
                    if not span_text or ":" in span_text:
                        continue
                    if re.search(r"vue|view|\d+[KMB]?\s*(vue|view)", span_text, re.IGNORECASE):
                        continue
                    upload_time = span_text
                    break
                if upload_time == "unknown":
                    thumb = element.query_selector("a#thumbnail")
                    if thumb:
                        aria = thumb.get_attribute("aria-label") or ""
                        time_match = re.search(
                            r"(\d+\s+(?:second|minute|hour|day|week|month|year|"
                            r"seconde|minute|heure|jour|semaine|mois|an)s?\s+ago"
                            r"|il y a \d+\s+\w+)", aria, re.IGNORECASE
                        )
                        if time_match:
                            upload_time = time_match.group(0)

                print(f"  [DEBUG] Extracted: {video_id} | {title[:40]} | upload: {upload_time}")

                if upload_time and not _is_recent(upload_time):
                    continue

                results.append({
                    "video_id": video_id,
                    "title": title,
                    "description": "",
                    "channel": channel_name,
                    "upload_time": upload_time,
                })
            except Exception as e:
                print(f"  [DEBUG] Element extraction error: {e}")
        return results

    if page is not None:
        return _scrape(page)

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            pg = context.new_page()
            patch_page(pg)
            return _scrape(pg)
        finally:
            context.close()


_GENERIC_PRAISE = re.compile(
    r"^[\s\W]*(great|amazing|awesome|excellent|love this|loved this|best channel|"
    r"too good|so good|very good|this is good|nice video|good video|great video|"
    r"great content|love your|love the|thank you|thanks for|well explained|"
    r"keep it up|keep up|you(\'re| are) (great|amazing|the best|so good)|"
    r"this channel|subscribed|just subscribed|new sub|new subscriber"
    r")[\s!.]*$",
    re.IGNORECASE,
)

_SUBSTANCE_KEYWORDS = re.compile(
    r"ship|freight|customs|import|export|supplier|sourcing|fba|amazon|logistics|"
    r"forwarder|incoterm|duty|tariff|cargo|container|warehouse|inventory|"
    r"product|order|cost|price|rate|fee|delay|clearance|inspection|compliance|"
    r"packaging|label|dimension|weight|broker|consolidat|courier|express|parcel",
    re.IGNORECASE,
)


_SPAM_PATTERNS = re.compile(
    r"i started (using|leveraging|trying|working with)\s+\w+|"
    r"(check out|try out|look into|visit|dm me for)\s+\w+|"
    r"\b(tool|platform|software|service|app|solution)\b.{0,30}\b(great|amazing|helped|changed|growth|visibility|brand)\b|"
    r"\b(growth|visibility|brand|awareness|reach|engagement)\b.{0,30}\b(tool|platform|software|app|solution)\b|"
    r"it'?s? (pure gold|a game[- ]changer|incredible|amazing|mind[- ]blowing)|"
    r"this video (is|has been) (pure gold|amazing|incredible)|"
    r"\b(dm|message) me\b|"
    r"link in (my |the )?(bio|description|profile)|"
    r"(free|join|sign up|register).{0,20}(trial|now|today|here)",
    re.IGNORECASE,
)

_FRENCH_MARKERS = re.compile(
    r"[àâçéèêëîïôœùûüÿÀÂÇÉÈÊËÎÏÔŒÙÛÜŸ]|"
    r"\b(avec|pour|comme|dans|aussi|très|tout|faire|avoir|être|aller|"
    r"vouloir|pouvoir|bonjour|voilà|donc|alors|après|avant|pendant|"
    r"toujours|jamais|vraiment|beaucoup|pourquoi|merci|notre|votre|"
    r"cette|depuis|plusieurs|même|moins|déjà)\b",
    re.IGNORECASE,
)


def _is_replyable(comment_text: str) -> bool:
    """Return True if the comment is English and has enough substance to warrant a reply."""
    text = comment_text.strip()
    if len(text) < 35:
        return False
    if _GENERIC_PRAISE.match(text):
        return False
    if _SPAM_PATTERNS.search(text):
        return False
    if not _SUBSTANCE_KEYWORDS.search(text):
        return False
    if not _is_english_title(text):  # filters Arabic, Chinese scripts
        return False
    if _FRENCH_MARKERS.search(text):  # skip French comments
        return False
    return True


def get_video_comments(video_id: str, max_results: int = 10, page=None) -> list:
    def _scrape(pg):
        results = []
        pg.goto(f"https://www.youtube.com/watch?v={video_id}")
        pg.wait_for_load_state("networkidle")

        for _ in range(4):
            pg.evaluate("window.scrollBy(0, 500)")
            time.sleep(1.5)

        pg.wait_for_selector("ytd-comment-thread-renderer", timeout=15000)

        threads = pg.query_selector_all("ytd-comment-thread-renderer")
        for thread in threads:
            if len(results) >= max_results:
                break

            comment_id = thread.get_attribute("id") or ""

            author_el = thread.query_selector("#author-text")
            author = (author_el.inner_text() if author_el else "").strip()

            text_el = thread.query_selector("#content-text")
            text = (text_el.inner_text() if text_el else "").strip()

            like_el = thread.query_selector("#vote-count-middle")
            like_text = (like_el.inner_text() if like_el else "").strip()
            try:
                like_count = int(like_text.replace(",", "")) if like_text else 0
            except ValueError:
                like_count = 0

            if not text or not _is_replyable(text):
                continue

            results.append({
                "comment_id": comment_id,
                "author": author,
                "text": text,
                "like_count": like_count,
            })
        return results

    if page is not None:
        return _scrape(page)

    with sync_playwright() as p:
        context = get_browser_context(p)
        try:
            pg = context.new_page()
            patch_page(pg)
            return _scrape(pg)
        finally:
            context.close()


def get_popular_videos_for_replies(max_results: int = 5, seen_ids: set = None, page=None) -> list:
    if seen_ids is None:
        seen_ids = set()
    popular = []
    for query in random.sample(SEARCH_QUERIES, min(5, len(SEARCH_QUERIES))):
        if len(popular) >= max_results:
            break
        videos = get_videos_by_keyword(query, max_results=15, page=page)
        for video in videos:
            if video["video_id"] in seen_ids:
                continue
            if not _is_english_title(video["title"]):
                continue
            if _FRENCH_MARKERS.search(video["title"]):
                continue
            count = _parse_view_count(video.get("view_count_text", ""))
            print(f"  [DEBUG] Reply candidate: {video['title'][:40]} | views raw: {video.get('view_count_text', '?')} → {count}")
            if count >= 5_000:
                popular.append(video)
            if len(popular) >= max_results:
                break
    return popular


if __name__ == "__main__":
    print("--- Testing keyword search ---")
    videos = get_videos_by_keyword("amazon fba china shipping", max_results=5)
    for v in videos:
        print(f"  {v['video_id']} | {v['title'][:60]} | {v['upload_time']}")

    print("\n--- Testing channel scrape (Jungle Scout) ---")
    videos = get_channel_recent_videos(
        "https://www.youtube.com/@JungleScout/videos", "Jungle Scout", max_results=2
    )
    for v in videos:
        print(f"  {v['video_id']} | {v['title'][:60]}")

    print("\n--- Testing comment scrape ---")
    comments = get_video_comments("dQw4w9WgXcQ", max_results=3)
    for c in comments:
        print(f"  [{c['like_count']} likes] {c['text'][:80]}")
