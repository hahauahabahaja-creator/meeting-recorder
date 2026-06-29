import os
import time
import sys
import random
import requests
import subprocess
from datetime import datetime
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth_sync

# ============================================
# ⚙️ CONFIGURATION & SECRETS
# ============================================
MEET_URL = os.environ.get("MEET_URL", "").strip()
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
REPO_NAME = os.environ.get("REPO_NAME", "").strip()
RENDER_URL = os.environ.get("RENDER_URL", "").strip()

# Default display name
BOT_NAME = os.environ.get("BOT_NAME", "Meeting Bot")

# ============================================
# 🛠️ HELPER FUNCTIONS
# ============================================
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def send_telegram(message):
    """Sends a text message updates to Telegram"""
    if BOT_TOKEN and CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'},
                timeout=10
            )
            log("✅ Telegram status update sent.")
        except Exception as e:
            log(f"⚠️ Telegram update sending failed: {e}")

def send_telegram_photo(photo_path, caption):
    """Sends a screenshot photo update to Telegram"""
    if BOT_TOKEN and CHAT_ID:
        try:
            with open(photo_path, 'rb') as f:
                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
                    data={'chat_id': CHAT_ID, 'caption': caption},
                    files={'photo': f},
                    timeout=30
                )
            log("✅ Telegram live screenshot sent.")
        except Exception as e:
            log(f"⚠️ Telegram screenshot sending failed: {e}")

def human_type(element, text):
    """Types text like a human with random delay between keys"""
    try:
        element.click()
        time.sleep(random.uniform(0.3, 0.7))
        if hasattr(element, "press_sequentially"):
            element.press_sequentially(text, delay=random.randint(70, 180))
        else:
            element.type(text, delay=random.randint(70, 180))
        log(f"✍️ Typed text: '{text}' successfully.")
    except Exception as e:
        log(f"ℹ️ Falling back to direct fill due to: {e}")
        try:
            element.fill(text)
        except Exception as fill_err:
            log(f"❌ Failed to fill text: {fill_err}")

def human_mouse_move(page):
    """Simulates realistic mouse movements to bypass bot-checks"""
    try:
        for _ in range(random.randint(2, 4)):
            page.mouse.move(random.randint(100, 1200), random.randint(100, 600))
            time.sleep(random.uniform(0.15, 0.35))
    except Exception as e:
        log(f"⚠️ Mouse movement simulation failed: {e}")

def generate_fake_video():
    """Generate a tiny .y4m fake video file for Chrome's fake camera"""
    fake_path = "/tmp/fake_camera.y4m"
    if os.path.exists(fake_path):
        return fake_path
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i",
            "color=c=black:s=320x240:d=1:r=1",
            "-pix_fmt", "yuv420p", fake_path
        ], capture_output=True, timeout=10)
        if os.path.exists(fake_path):
            log("✅ Fake camera video file generated.")
            return fake_path
    except Exception as e:
        log(f"⚠️ Could not generate fake video: {e}")
    return None

# ============================================
# 🐙 GITHUB ACTION VARIABLE SYSTEM
# ============================================
def get_github_variable(var_name):
    """Fetches a variable value from GitHub Repository Variables"""
    if not GITHUB_TOKEN or not REPO_NAME:
        return None
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("value", "")
    except Exception as e:
        log(f"⚠️ Error reading GitHub variable {var_name}: {e}")
    return None

def set_github_variable(var_name, value):
    """Updates a variable value in GitHub Repository Variables"""
    if not GITHUB_TOKEN or not REPO_NAME:
        return False
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        res = requests.patch(url, json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        if res.status_code == 204:
            return True
    except Exception as e:
        log(f"⚠️ Error setting GitHub variable {var_name}: {e}")
    return False

cached_command_response = None
cached_time = 0

def get_command_flag(var_name):
    """Fetches command flags directly from Render polling or falls back to GitHub Variables"""
    global cached_command_response, cached_time
    current_time = time.time()
    
    if RENDER_URL:
        if cached_command_response is None or (current_time - cached_time) > 2:
            try:
                endpoint = RENDER_URL.rstrip('/') + '/api/command'
                res = requests.get(endpoint, timeout=5)
                if res.status_code == 200:
                    cached_command_response = res.json()
                    cached_time = current_time
                else:
                    cached_command_response = None
            except Exception as e:
                log(f"⚠️ Error polling Render command API: {e}")
                cached_command_response = None

    if cached_command_response:
        key = var_name.lower().replace("_flag", "")
        val = cached_command_response.get(key)
        if val is not None:
            return str(val)

    return get_github_variable(var_name)

# ============================================
# 🧬 PLATFORM DETECTOR & FORMATTER
# ============================================
def get_platform(url):
    url_lower = url.lower()
    if "meet.google.com" in url_lower:
        return "google"
    elif "zoom.us" in url_lower:
        return "zoom"
    elif "teams.microsoft.com" in url_lower or "teams.live.com" in url_lower:
        return "teams"
    return "unknown"

def format_zoom_url(url):
    """Converts a standard Zoom join URL to a web client URL"""
    if "zoom.us/j/" in url:
        import re
        match = re.search(r'/j/(\d+)', url)
        if match:
            meeting_id = match.group(1)
            pwd = ""
            if "pwd=" in url:
                parts = url.split("pwd=")
                if len(parts) > 1:
                    pwd = parts[1].split("&")[0]
            web_url = f"https://zoom.us/wc/{meeting_id}/join"
            if pwd:
                web_url += f"?pwd={pwd}"
            log(f"🔄 Reformatted Zoom Join Link to Web client: {web_url}")
            return web_url
    return url

# ============================================
# 🚀 RESOURCE BLOCKER (Speed Boost)
# ============================================
BLOCKED_DOMAINS = [
    "google-analytics.com",
    "googletagmanager.com",
    "doubleclick.net",
    "facebook.net",
    "connect.facebook.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
]

def setup_resource_blocker(page):
    """Block heavy non-essential resources to free up CPU"""
    def handle_route(route):
        url = route.request.url
        resource_type = route.request.resource_type
        
        # Block tracking & analytics domains
        for domain in BLOCKED_DOMAINS:
            if domain in url:
                route.abort()
                return
        
        # Block images and fonts (not needed for joining)
        if resource_type in ["image", "font"]:
            route.abort()
            return
        
        route.continue_()
    
    page.route("**/*", handle_route)
    log("🛡️ Resource blocker active (analytics, fonts, images blocked)")

# ============================================
# 🚀 GOOGLE MEET AUTOMATION (REWRITTEN)
# ============================================
def automate_google_meet(page, url):
    log("📡 Automating Google Meet...")
    
    # Block heavy resources before navigating
    setup_resource_blocker(page)
    
    # Navigate using domcontentloaded (don't wait for all resources)
    log("🌐 Loading Google Meet page...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    log("✅ DOM loaded. Waiting for Meet UI to initialize...")
    
    # Smart polling: wait for ANY interactive element with retries
    max_wait = 120  # 2 minutes max
    poll_interval = 3
    elapsed = 0
    element_found = False
    
    while elapsed < max_wait:
        # Check if name input OR join button exists in DOM (even if not visible)
        found = page.evaluate("""
            () => {
                let input = document.querySelector('input[type="text"][placeholder]');
                let joinBtn = [...document.querySelectorAll('button')].find(
                    b => (b.innerText || '').match(/join|ask/i)
                );
                return {
                    hasInput: !!input,
                    hasJoin: !!joinBtn,
                    inputPlaceholder: input ? input.placeholder : '',
                    joinText: joinBtn ? joinBtn.innerText.trim() : ''
                };
            }
        """)
        
        if found.get("hasInput") or found.get("hasJoin"):
            log(f"✅ Meet UI detected! Input: {found.get('inputPlaceholder', 'N/A')}, Button: {found.get('joinText', 'N/A')}")
            element_found = True
            break
        
        log(f"⏳ Waiting for Meet UI... ({elapsed}s / {max_wait}s)")
        page.wait_for_timeout(poll_interval * 1000)
        elapsed += poll_interval
    
    if not element_found:
        log("⚠️ Meet UI elements not found after 2 minutes. Attempting to proceed anyway...")
    
    page.wait_for_timeout(2000)
    
    # 1. Dismiss any dialogs (Got it, Dismiss, etc.)
    log("🔄 Dismissing dialogs...")
    page.evaluate("""
        () => {
            document.querySelectorAll('button').forEach(btn => {
                let txt = (btn.innerText || '').toLowerCase();
                if (txt.includes('got it') || txt.includes('dismiss') || txt.includes('i understand') || txt.includes('ok')) {
                    btn.click();
                }
            });
        }
    """)
    page.wait_for_timeout(1000)
    
    # 2. Turn off mic and camera via keyboard shortcuts
    log("🔇 Muting microphone & camera...")
    try:
        page.click('body', timeout=3000)
        page.wait_for_timeout(500)
        page.keyboard.press("Control+d")
        page.wait_for_timeout(500)
        page.keyboard.press("Control+e")
        page.wait_for_timeout(1000)
    except Exception as e:
        log(f"⚠️ Keyboard shortcuts failed: {e}")
    
    # Also try clicking mic/camera toggle buttons directly via JS
    page.evaluate("""
        () => {
            // Find and click mic/camera toggle buttons by aria-label
            document.querySelectorAll('[aria-label*="microphone"], [aria-label*="camera"], [data-tooltip*="microphone"], [data-tooltip*="camera"]').forEach(el => {
                if (el.tagName === 'BUTTON' || el.closest('button')) {
                    (el.closest('button') || el).click();
                }
            });
        }
    """)
    page.wait_for_timeout(1000)
    
    # 3. Enter guest name using multiple strategies
    log("✍️ Entering display name...")
    name_entered = False
    
    # Strategy A: Direct Playwright interaction
    try:
        name_input = page.locator('input[type="text"]').first
        if name_input.is_visible(timeout=3000):
            name_input.click()
            name_input.fill("")
            human_type(name_input, BOT_NAME)
            name_entered = True
            log("✅ Name typed via Playwright.")
    except:
        pass
    
    # Strategy B: JavaScript forced entry with React-compatible events
    if not name_entered:
        log("✍️ Trying JS name injection...")
        result = page.evaluate("""
            (botName) => {
                let inputs = document.querySelectorAll('input[type="text"]');
                for (let input of inputs) {
                    // Use React's native input setter to bypass virtual DOM
                    let nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    nativeInputValueSetter.call(input, botName);
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true }));
                    return true;
                }
                return false;
            }
        """, BOT_NAME)
        if result:
            name_entered = True
            log("✅ Name injected via JS.")
        else:
            log("⚠️ No text input found for name.")
    
    page.wait_for_timeout(2000)
    
    # 4. Click Join/Ask to join button with multiple strategies
    log("⏳ Attempting to join meeting...")
    human_mouse_move(page)
    joined = False
    
    # Strategy A: Playwright locators
    join_selectors = [
        "button:has-text('Ask to join')",
        "button:has-text('Join now')",
        "button:has-text('Join')",
        "button:has-text('Ask')",
    ]
    for sel in join_selectors:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                log(f"✅ Joined via Playwright: {sel}")
                joined = True
                break
        except:
            continue
    
    # Strategy B: JavaScript click with retry
    if not joined:
        log("⚠️ Trying JS join click...")
        for attempt in range(3):
            result = page.evaluate("""
                () => {
                    let btns = [...document.querySelectorAll('button')];
                    let joinBtn = btns.find(b => {
                        let txt = (b.innerText || '').toLowerCase();
                        return (txt.includes('join') || txt.includes('ask')) && !b.disabled;
                    });
                    if (joinBtn) {
                        joinBtn.scrollIntoView();
                        joinBtn.focus();
                        joinBtn.click();
                        return joinBtn.innerText.trim();
                    }
                    return null;
                }
            """)
            if result:
                log(f"✅ Joined via JS click: '{result}' (attempt {attempt+1})")
                joined = True
                break
            page.wait_for_timeout(2000)
    
    # Strategy C: Simulate Enter key on the name field
    if not joined:
        log("⚠️ Trying Enter key submission...")
        try:
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
            page.keyboard.press("Enter")
            page.wait_for_timeout(2000)
            log("✅ Submitted via Enter key.")
            joined = True
        except:
            pass
    
    if not joined:
        log("❌ Could not join Google Meet after all strategies.")
    else:
        # Wait a moment to confirm we're in the meeting
        page.wait_for_timeout(5000)
        log("🎯 Google Meet join sequence completed.")

# ============================================
# 🚀 ZOOM AUTOMATION
# ============================================
def automate_zoom(page, url):
    log("📡 Automating Zoom...")
    target_url = format_zoom_url(url)
    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(10000)

    # Handle Cookies & TOS
    log("🔄 Managing Cookie consents...")
    try:
        cookie_btn = page.locator('#onetrust-accept-btn-handler').first
        if cookie_btn.is_visible(timeout=3000):
            cookie_btn.click()
            log("✅ Cookies accepted.")
    except:
        pass

    try:
        agree_btn = page.locator('#wc_agree1').first
        if agree_btn.is_visible(timeout=3000):
            agree_btn.click()
            log("✅ Zoom Terms agreed.")
    except:
        pass

    # Turn off Microphone
    log("🔇 Muting audio pre-join...")
    try:
        mute_btn = page.locator('#preview-audio-control-button').first
        if mute_btn.is_visible(timeout=3000):
            mute_btn.click()
            log("✅ Muted.")
    except Exception as e:
        log(f"ℹ️ Pre-join mute skipped: {e}")

    # Turn off Camera
    log("📹 Turning off camera pre-join...")
    try:
        cam_btn = page.locator('#preview-video-control-button').first
        if cam_btn.is_visible(timeout=3000):
            cam_btn.click()
            log("✅ Camera turned off.")
    except Exception as e:
        log(f"ℹ️ Pre-join camera off skipped: {e}")

    # Enter Name
    try:
        name_input = page.locator('#input-for-name').first
        if name_input.is_visible(timeout=3000):
            human_type(name_input, BOT_NAME)
            page.wait_for_timeout(1000)
    except Exception as e:
        log(f"⚠️ Could not find Zoom name input: {e}")

    # Click Join
    log("⏳ Joining Zoom Session...")
    human_mouse_move(page)
    try:
        join_btn = page.locator('button.zm-btn.preview-join-button').first
        if join_btn.is_visible(timeout=3000):
            join_btn.click()
            log("✅ Clicked Zoom join.")
            page.wait_for_timeout(5000)
    except Exception as e:
        log(f"❌ Failed to click Zoom join: {e}")

    # Join Audio by Computer inside meeting
    try:
        audio_computer = page.locator('button:has-text("Join Audio by Computer")').first
        if audio_computer.is_visible(timeout=10000):
            audio_computer.click()
            log("✅ Joined Audio by Computer successfully.")
    except:
        pass

# ============================================
# 🚀 TEAMS AUTOMATION
# ============================================
def automate_teams(page, url):
    log("📡 Automating Microsoft Teams...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(10000)

    # 1. Fill Name
    try:
        name_input = page.locator('[data-tid="prejoin-display-name-input"]').first
        if name_input.is_visible(timeout=5000):
            human_type(name_input, BOT_NAME)
            page.wait_for_timeout(1000)
    except Exception as e:
        log(f"⚠️ Teams name input not found: {e}")

    # 2. Mute Mic
    try:
        mute_btn = page.locator('[data-tid="toggle-mute"]').first
        if mute_btn.is_visible(timeout=3000):
            mute_btn.click()
            log("✅ Teams audio muted.")
            page.wait_for_timeout(1000)
    except:
        pass

    # 3. Join
    try:
        join_btn = page.locator('[data-tid="prejoin-join-button"]').first
        if join_btn.is_visible(timeout=3000):
            human_mouse_move(page)
            join_btn.click()
            log("✅ Clicked Teams Join Button.")
    except Exception as e:
        log(f"❌ Failed to join Teams: {e}")

# ============================================
# 🔄 MAIN LOOP & EVENT MONITOR
# ============================================
def run_bot():
    if not MEET_URL:
        log("❌ Error: MEET_URL env var is missing!")
        return

    platform = get_platform(MEET_URL)
    log(f"📡 Target platform detected: {platform.upper()}")
    
    send_telegram(f"🚀 **Bot Started**\n📡 Platform: `{platform.upper()}`\n🔗 URL: `{MEET_URL}`")

    # Generate fake camera video file
    fake_video = generate_fake_video()

    with sync_playwright() as p:
        log("🌐 Launching Playwright Chromium Browser...")
        
        # Build launch args
        launch_args = [
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1366,768",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--enable-unsafe-swiftshader",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
            "--autoplay-policy=no-user-gesture-required",
        ]
        
        # If fake video exists, use it for camera
        if fake_video:
            launch_args.append(f"--use-file-for-fake-video-capture={fake_video}")
        
        browser = p.chromium.launch(
            headless=False,
            args=launch_args
        )

        context = browser.new_context(
            viewport={'width': 1366, 'height': 768},
            permissions=['camera', 'microphone'],
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            extra_http_headers={
                "sec-ch-ua": '"Chromium";v="122", "Google Chrome";v="122", "Not/A)Brand";v="99"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Linux"'
            },
            locale="en-US",
            timezone_id="UTC"
        )
        
        # Spoof navigator.webdriver globally
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined })")
        
        page = context.new_page()
        
        # Apply Stealth Plugin overrides
        stealth_sync(page)

        # Execute platform automation
        if platform == "google":
            automate_google_meet(page, MEET_URL)
        elif platform == "zoom":
            automate_zoom(page, MEET_URL)
        elif platform == "teams":
            automate_teams(page, MEET_URL)
        else:
            log("📡 Generic browser load for unknown platform...")
            page.goto(MEET_URL, timeout=60000)

        # Notify Telegram we are inside
        send_telegram(f"✅ **Session Joined Successfully!**\n🎥 Recording is now active.")

        # Monitoring Loop
        log("🔄 Monitoring meeting status & GitHub flags...")
        start_time = time.time()
        max_time = 18000 # 5 Hours max safety
        
        while time.time() - start_time < max_time:
            # 1. Check STOP_FLAG
            stop_val = get_command_flag("STOP_FLAG")
            if stop_val == "1":
                log("🛑 STOP_FLAG detected! Exiting bot.")
                send_telegram("🛑 **Stop Command Received.** Finishing recording...")
                break

            # 2. Check VIEW_FLAG (Live Screenshot)
            view_val = get_command_flag("VIEW_FLAG")
            if view_val == "1":
                log("📸 VIEW_FLAG detected! Capturing screenshot...")
                try:
                    screenshot_path = "live_view.png"
                    page.screenshot(path=screenshot_path)
                    send_telegram_photo(screenshot_path, f"📸 **Live view at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
                    if os.path.exists(screenshot_path):
                        os.remove(screenshot_path)
                except Exception as e:
                    log(f"⚠️ Screenshot capture failed: {e}")
                finally:
                    set_github_variable("VIEW_FLAG", "0")

            # 3. Check FULL_FLAG (Toggle Fullscreen)
            full_val = get_command_flag("FULL_FLAG")
            if full_val == "1":
                log("📺 FULL_FLAG detected! Toggling Fullscreen...")
                try:
                    page.evaluate("document.documentElement.requestFullscreen().catch(() => {})")
                    send_telegram("📺 **Display mode set to Full Screen.**")
                except Exception as e:
                    log(f"⚠️ Fullscreen toggle failed: {e}")
                finally:
                    set_github_variable("FULL_FLAG", "0")

            # Sleep before next check
            time.sleep(10)

        log("🧹 Closing browser context...")
        browser.close()
        log("🏁 Bot closed successfully.")

if __name__ == "__main__":
    run_bot()
