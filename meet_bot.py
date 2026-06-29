import os
import time
import sys
import random
import requests
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
        # Use press_sequentially for modern playwright, fallback to type/fill
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
        width = 1366
        height = 768
        for _ in range(random.randint(2, 4)):
            page.mouse.move(random.randint(50, width-50), random.randint(50, height-50))
            time.sleep(random.uniform(0.2, 0.5))
    except Exception as e:
        log(f"⚠️ Mouse movement simulation failed: {e}")

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
        # Fetch every 2 seconds at max
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
# 🚀 AUTOMATION STEPS
# ============================================
def automate_google_meet(page, url):
    log("📡 Automating Google Meet...")
    page.goto(url, timeout=60000)
    
    log("⏳ Waiting for Google Meet page to finish loading...")
    try:
        # Wait up to 45 seconds for either the name input field OR a Join button to appear
        page.wait_for_selector('input[type="text"], button:has-text("Join"), button:has-text("Ask")', timeout=45000)
        log("✅ Google Meet pre-join page elements detected.")
    except Exception as e:
        log(f"⚠️ Page loading timed out or elements not found: {e}")
        
    page.wait_for_timeout(3000)

    # 1. Dismiss Dialog/Popup (Dismiss, Got it)
    log("🔄 Checking for dialogs...")
    try:
        page.evaluate("""
            () => {
                document.querySelectorAll('button').forEach(btn => {
                    let txt = btn.innerText || '';
                    if (txt.includes('Got it') || txt.includes('Dismiss') || txt.includes('I understand')) {
                        btn.click();
                    }
                });
            }
        """)
    except:
        pass

    # 2. Focus and Turn off mic and camera (Ctrl+d and Ctrl+e)
    log("🔇 Muting microphone & shutting down camera...")
    try:
        # Click body to ensure keyboard focus is on the page
        page.click('body')
        page.wait_for_timeout(1000)
        page.keyboard.press("Control+d")
        page.wait_for_timeout(1000)
        page.keyboard.press("Control+e")
        page.wait_for_timeout(2000)
    except Exception as e:
        log(f"⚠️ Could not use shortcuts: {e}")

    # 3. Enter Guest Name
    name_entered = False
    try:
        name_input = page.locator('input[type="text"]').first
        if name_input.is_visible(timeout=5000):
            log("✍️ Typing display name...")
            human_type(name_input, BOT_NAME)
            name_entered = True
            page.wait_for_timeout(1000)
    except Exception as e:
        log(f"ℹ️ Standard guest name entry skipped or failed: {e}")

    # Fallback to JavaScript if standard entry was skipped or failed
    if not name_entered:
        log("✍️ Attempting JavaScript forced name entry...")
        try:
            res = page.evaluate(f"""
                (bot_name) => {{
                    let input = document.querySelector('input[type="text"]');
                    if (input) {{
                        input.value = bot_name;
                        input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                        input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        return true;
                    }}
                    return false;
                }}
            """, BOT_NAME)
            if res:
                log("✅ Name entered using JS.")
                page.wait_for_timeout(2000)
            else:
                log("⚠️ JS could not find the guest name input field.")
        except Exception as e:
            log(f"⚠️ JavaScript name entry failed: {e}")

    # 4. Join the meeting
    log("⏳ Attempting to Join Google Meet call...")
    human_mouse_move(page)
    joined = False
    selectors = ["text=Ask to join", "text=Join now", "button:has-text('Join')", "button:has-text('Ask')"]
    
    for selector in selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=5000):
                btn.click()
                log(f"✅ Clicked Join using: {selector}")
                joined = True
                break
        except:
            continue

    if not joined:
        log("⚠️ Trying JavaScript forced join...")
        try:
            # Let's add a small wait to ensure button is enabled after input event
            page.wait_for_timeout(2000)
            res = page.evaluate("""
                () => {
                    let btns = [...document.querySelectorAll('button')];
                    let jBtn = btns.find(b => b.innerText.includes('Join') || b.innerText.includes('Ask'));
                    if(jBtn) {
                        jBtn.click();
                        return true;
                    }
                    return false;
                }
            """)
            if res:
                log("✅ Clicked Join using JS.")
                joined = True
            else:
                log("⚠️ JS could not find the Join/Ask button.")
        except Exception as e:
            log(f"⚠️ JavaScript forced join failed: {e}")

    if not joined:
        log("❌ Failed to join Google Meet.")

def automate_zoom(page, url):
    log("📡 Automating Zoom...")
    target_url = format_zoom_url(url)
    page.goto(target_url, timeout=60000)
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

def automate_teams(page, url):
    log("📡 Automating Microsoft Teams...")
    page.goto(url, timeout=60000)
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

    with sync_playwright() as p:
        log("🌐 Launching Playwright Chromium Browser...")
        
        # Standard configuration to run undetected
        browser = p.chromium.launch(
            headless=False, # Xvfb handles the GUI display in actions
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1366,768",
                "--mute-audio",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-webgl",
                "--disable-3d-apis",
                "--use-gl=angle",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader"
            ]
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
        
        # Spoof navigator.webdriver globally for all context windows/iframes
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', { get: () => undefined })")
        
        page = context.new_page()
        
        # Apply standard Stealth Plugin overrides
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
