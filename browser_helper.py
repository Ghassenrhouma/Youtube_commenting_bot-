import random
import time
import os
from dotenv import load_dotenv

load_dotenv()

PROFILE_PATH = os.getenv("PROFILE_PATH", "profiles/default")
HEADLESS = os.getenv("HEADLESS", "True").lower() == "true"


def get_browser_context(playwright):
    os.makedirs(PROFILE_PATH, exist_ok=True)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=PROFILE_PATH,
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--autoplay-policy=no-user-gesture-required",
            "--window-size=1280,800",
            "--lang=en-US",
        ],
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/134.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
        locale="en-US",
        timezone_id="America/New_York",
        extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
    )
    return context


def patch_page(page):
    # Randomised canvas noise seed — unique per session so fingerprint differs each run
    noise = random.randint(1, 10)
    page.add_init_script(f"""
        // ── webdriver flag ────────────────────────────────────────────────────
        Object.defineProperty(navigator, 'webdriver', {{get: () => undefined}});

        // ── plugins — mimic a real Chrome install ─────────────────────────────
        Object.defineProperty(navigator, 'plugins', {{
            get: () => {{
                const makePlugin = (name, filename, desc, mimeType, suffix) => {{
                    const mime = {{ type: mimeType, suffixes: suffix, description: desc,
                                   enabledPlugin: null }};
                    const plugin = {{ name, filename, description: desc, length: 1, 0: mime,
                                     item: i => i === 0 ? mime : undefined,
                                     namedItem: n => n === mimeType ? mime : undefined,
                                     [Symbol.iterator]: function*() {{ yield mime; }} }};
                    mime.enabledPlugin = plugin;
                    return plugin;
                }};
                const list = [
                    makePlugin('PDF Viewer','internal-pdf-viewer','Portable Document Format','application/pdf','pdf'),
                    makePlugin('Chrome PDF Viewer','internal-pdf-viewer','Portable Document Format','application/x-google-chrome-pdf','pdf'),
                    makePlugin('Chromium PDF Viewer','internal-pdf-viewer','Portable Document Format','application/x-chromium-pdf','pdf'),
                    makePlugin('Microsoft Edge PDF Viewer','internal-pdf-viewer','Portable Document Format','application/x-edge-pdf','pdf'),
                    makePlugin('WebKit built-in PDF','internal-pdf-viewer','Portable Document Format','application/x-webkit-pdf','pdf'),
                ];
                Object.defineProperty(list, 'length', {{value: list.length}});
                list.item = i => list[i];
                list.namedItem = n => list.find(p => p.name === n) || null;
                list[Symbol.iterator] = function*() {{ for (const p of Array.from({{length: list.length}}, (_, i) => list[i])) yield p; }};
                return list;
            }}
        }});

        // ── languages / platform ──────────────────────────────────────────────
        Object.defineProperty(navigator, 'languages', {{get: () => ['en-US', 'en']}});
        Object.defineProperty(navigator, 'platform',  {{get: () => 'Win32'}});

        // ── hardware — realistic mid-range laptop values ───────────────────────
        Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => 8}});
        Object.defineProperty(navigator, 'deviceMemory',        {{get: () => 8}});

        // ── screen — match the viewport set in get_browser_context ───────────
        Object.defineProperty(screen, 'width',       {{get: () => 1280}});
        Object.defineProperty(screen, 'height',      {{get: () => 800}});
        Object.defineProperty(screen, 'availWidth',  {{get: () => 1280}});
        Object.defineProperty(screen, 'availHeight', {{get: () => 760}});
        Object.defineProperty(screen, 'colorDepth',  {{get: () => 24}});
        Object.defineProperty(screen, 'pixelDepth',  {{get: () => 24}});

        // ── chrome runtime — fuller stub ──────────────────────────────────────
        window.chrome = {{
            runtime: {{
                connect: () => {{}},
                sendMessage: () => {{}},
                onMessage: {{ addListener: () => {{}}, removeListener: () => {{}} }},
            }},
            loadTimes: () => ({{
                requestTime: Date.now() / 1000 - Math.random() * 0.5,
                startLoadTime: Date.now() / 1000 - Math.random() * 0.3,
                commitLoadTime: Date.now() / 1000 - Math.random() * 0.1,
                finishDocumentLoadTime: Date.now() / 1000,
                finishLoadTime: Date.now() / 1000 + Math.random() * 0.1,
                firstPaintTime: Date.now() / 1000 - Math.random() * 0.2,
                firstPaintAfterLoadTime: 0,
                navigationType: 'Other',
                wasFetchedViaSpdy: false,
                wasNpnNegotiated: false,
                npnNegotiatedProtocol: 'h2',
                wasAlternateProtocolAvailable: false,
                connectionInfo: 'h2',
            }}),
            csi: () => ({{ startE: Date.now(), onloadT: Date.now(), pageT: Math.random() * 3000, tran: 15 }}),
            app: {{ isInstalled: false, InstallState: {{}}, RunningState: {{}} }},
        }};

        // ── canvas fingerprint — noise only on toDataURL (not getImageData) ──
        // getImageData is patched by some sites for DRM checks — do not modify it
        const _noise = {noise};
        const _origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function(type, ...args) {{
            const ctx = this.getContext('2d');
            if (ctx) {{
                const imgData = ctx.getImageData(0, 0, this.width || 1, this.height || 1);
                imgData.data[0] = (imgData.data[0] + _noise) % 256;
                imgData.data[1] = (imgData.data[1] + _noise) % 256;
                ctx.putImageData(imgData, 0, 0);
            }}
            return _origToDataURL.call(this, type, ...args);
        }};

        // ── WebGL fingerprint — spoof vendor & renderer ───────────────────────
        const _origGetParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(param) {{
            if (param === 37445) return 'Intel Inc.';
            if (param === 37446) return 'Intel Iris OpenGL Engine';
            return _origGetParam.call(this, param);
        }};
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            const _origGetParam2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function(param) {{
                if (param === 37445) return 'Intel Inc.';
                if (param === 37446) return 'Intel Iris OpenGL Engine';
                return _origGetParam2.call(this, param);
            }};
        }}

        // ── Permissions API — return 'prompt' instead of revealing automation ─
        if (navigator.permissions && navigator.permissions.query) {{
            const _origQuery = navigator.permissions.query.bind(navigator.permissions);
            navigator.permissions.query = (params) => {{
                if (params && params.name === 'notifications') {{
                    return Promise.resolve({{ state: 'prompt', onchange: null }});
                }}
                return _origQuery(params);
            }};
        }}

        // AudioContext noise patch removed — interferes with YouTube's audio pipeline

        // ── window outer dimensions — match viewport ──────────────────────────
        Object.defineProperty(window, 'outerWidth',  {{get: () => 1280}});
        Object.defineProperty(window, 'outerHeight', {{get: () => 800}});
        Object.defineProperty(window, 'innerWidth',  {{get: () => 1280}});
        Object.defineProperty(window, 'innerHeight', {{get: () => 800}});

        // ── navigator misc — realistic desktop values ─────────────────────────
        Object.defineProperty(navigator, 'maxTouchPoints', {{get: () => 0}});
        Object.defineProperty(navigator, 'cookieEnabled',  {{get: () => true}});
        Object.defineProperty(navigator, 'onLine',         {{get: () => true}});
        Object.defineProperty(navigator, 'doNotTrack',     {{get: () => null}});
        Object.defineProperty(navigator, 'appName',        {{get: () => 'Netscape'}});
        Object.defineProperty(navigator, 'appVersion',     {{get: () => '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'}});
        Object.defineProperty(navigator, 'product',        {{get: () => 'Gecko'}});
        Object.defineProperty(navigator, 'productSub',     {{get: () => '20030107'}});
        Object.defineProperty(navigator, 'vendor',         {{get: () => 'Google Inc.'}});
        Object.defineProperty(navigator, 'vendorSub',      {{get: () => ''}});

        // ── Connection API — mimic a typical home broadband connection ─────────
        if (navigator.connection) {{
            Object.defineProperty(navigator.connection, 'effectiveType', {{get: () => '4g'}});
            Object.defineProperty(navigator.connection, 'rtt',           {{get: () => 50}});
            Object.defineProperty(navigator.connection, 'downlink',      {{get: () => 10}});
            Object.defineProperty(navigator.connection, 'saveData',      {{get: () => false}});
        }}

        // ── Battery API — stub so it doesn't reveal automation ────────────────
        if (navigator.getBattery) {{
            navigator.getBattery = () => Promise.resolve({{
                charging: true,
                chargingTime: 0,
                dischargingTime: Infinity,
                level: 1.0,
                addEventListener: () => {{}},
                removeEventListener: () => {{}},
            }});
        }}

        // ── Media devices — return realistic fake devices instead of empty ────
        if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
            navigator.mediaDevices.enumerateDevices = () => Promise.resolve([
                {{deviceId: 'default', groupId: 'default', kind: 'audioinput',  label: ''}},
                {{deviceId: 'default', groupId: 'default', kind: 'audiooutput', label: ''}},
                {{deviceId: 'default', groupId: 'default', kind: 'videoinput',  label: ''}},
            ]);
        }}

        // ── mimeTypes — match the plugins stub ───────────────────────────────
        Object.defineProperty(navigator, 'mimeTypes', {{
            get: () => {{
                const types = [
                    {{ type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null }},
                    {{ type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null }},
                ];
                types.length = types.length;
                types.item = i => types[i];
                types.namedItem = n => types.find(m => m.type === n) || null;
                return types;
            }}
        }});

        // ── Performance / navigation timing — hide automation gaps ───────────
        if (window.performance && window.performance.getEntriesByType) {{
            const _origGetEntries = window.performance.getEntriesByType.bind(window.performance);
            window.performance.getEntriesByType = function(type) {{
                const entries = _origGetEntries(type);
                if (type === 'navigation' && entries.length > 0) {{
                    // Automation shows 0ms domInteractive gaps — add small realistic jitter
                    try {{
                        Object.defineProperty(entries[0], 'domInteractive', {{
                            get: () => entries[0].responseEnd + Math.random() * 200 + 50
                        }});
                    }} catch(e) {{}}
                }}
                return entries;
            }};
        }}
    """)


def _bezier_mouse_to(page, target_x, target_y):
    """Move mouse along a quadratic bezier curve to (target_x, target_y)."""
    start_x = random.randint(300, 900)
    start_y = random.randint(200, 500)
    cp_x = (start_x + target_x) / 2 + random.randint(-120, 120)
    cp_y = (start_y + target_y) / 2 + random.randint(-80, 80)
    steps = random.randint(12, 22)
    for i in range(steps + 1):
        t = i / steps
        mx = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * cp_x + t ** 2 * target_x
        my = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * cp_y + t ** 2 * target_y
        jitter = 1 - t
        mx += random.uniform(-3, 3) * jitter
        my += random.uniform(-2, 2) * jitter
        page.mouse.move(mx, my)
        time.sleep(random.uniform(0.008, 0.025))


def human_click(page, selector):
    """Move mouse via bezier curve to element then click."""
    try:
        el = page.query_selector(selector)
        if el:
            box = el.bounding_box()
            if box:
                tx = box["x"] + box["width"] * random.uniform(0.3, 0.7)
                ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
                _bezier_mouse_to(page, tx, ty)
                time.sleep(random.uniform(0.05, 0.15))
                page.mouse.click(tx, ty)
                return
    except Exception:
        pass
    page.click(selector)


def human_click_element(page, element):
    """Move mouse via bezier curve to a element handle then click it."""
    try:
        box = element.bounding_box()
        if box:
            tx = box["x"] + box["width"] * random.uniform(0.3, 0.7)
            ty = box["y"] + box["height"] * random.uniform(0.3, 0.7)
            _bezier_mouse_to(page, tx, ty)
            time.sleep(random.uniform(0.05, 0.15))
            page.mouse.click(tx, ty)
            return
    except Exception:
        pass
    element.click()


def human_scroll(page):
    time.sleep(random.uniform(0.8, 2.0))
    scroll_steps = random.randint(3, 6)
    for _ in range(scroll_steps):
        distance = random.randint(180, 420)
        increments = random.randint(3, 7)
        for _ in range(increments):
            page.evaluate(f"window.scrollBy(0, {distance // increments})")
            time.sleep(random.uniform(0.02, 0.08))
        time.sleep(random.uniform(0.6, 1.8))
    if random.random() < 0.35:
        back = random.randint(80, 200)
        page.evaluate(f"window.scrollBy(0, -{back})")
        time.sleep(random.uniform(0.5, 1.2))
        page.evaluate(f"window.scrollBy(0, {back})")
        time.sleep(random.uniform(0.4, 1.0))
    if random.random() < 0.2:
        time.sleep(random.uniform(2.0, 4.0))


def human_type(page, selector, text):
    """Click element then type with realistic human-like cadence."""
    human_click(page, selector)
    time.sleep(random.uniform(0.5, 1.2))

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


if __name__ == "__main__":
    print("browser_helper loaded")
