import os
import time
import requests
import subprocess
import random
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
BOT_NAME = os.environ.get("BOT_NAME", "Meeting Guest")

# ============================================
# 🛠️ HELPER FUNCTIONS
# ============================================
def log(message):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

def send_telegram(message):
    if BOT_TOKEN and CHAT_ID:
        try:
            requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                data={'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'},
                timeout=10
            )
        except Exception as e:
            log(f"⚠️ Telegram update failed: {e}")

def set_github_variable(var_name, value):
    if not GITHUB_TOKEN or not REPO_NAME: return False
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.patch(url, json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        return res.status_code == 204
    except Exception as e:
        log(f"⚠️ Error setting GitHub variable {var_name}: {e}")
    return False

cached_command_response = None
cached_time = 0

def get_command_flag(var_name):
    global cached_command_response, cached_time
    current_time = time.time()
    if RENDER_URL and (cached_command_response is None or (current_time - cached_time) > 3):
        try:
            res = requests.get(RENDER_URL.rstrip('/') + '/api/command', timeout=5)
            if res.status_code == 200:
                cached_command_response = res.json()
                cached_time = current_time
        except:
            cached_command_response = None

    if cached_command_response:
        key = var_name.lower().replace("_flag", "")
        val = cached_command_response.get(key)
        if val is not None: return str(val)

    # Fallback to GitHub Variables
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200: return res.json().get("value", "0")
    except: pass
    return "0"

# ============================================
# 🎥 RECORDING CONTROL
# ============================================
ffmpeg_process = None

def start_recording():
    global ffmpeg_process
    if ffmpeg_process: return
    log("🎥 Starting high-quality recording...")
    try:
        # Optimized for quality and low lag on lightweight setup
        cmd = [
            "ffmpeg", "-y", "-thread_queue_size", "4096",
            "-f", "x11grab", "-video_size", "1280x720", "-framerate", "30", "-i", ":99",
            "-f", "pulse", "-i", "default",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "output.mp4"
        ]
        ffmpeg_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log(f"✅ Recording started (PID: {ffmpeg_process.pid})")

        # Kill RDP for maximum performance
        log("🧹 Disabling RDP for maximum performance...")
        subprocess.run("pkill -f websockify", shell=True)
        subprocess.run("pkill -f x11vnc", shell=True)
        send_telegram("⏺️ **Recording started.** RDP services stopped to ensure zero-lag capture.")
    except Exception as e:
        log(f"❌ Failed to start recording: {e}")

def stop_recording():
    global ffmpeg_process
    if not ffmpeg_process: return
    log("🛑 Stopping recording...")
    try:
        ffmpeg_process.terminate()
        ffmpeg_process.wait(timeout=20)
        log("✅ Recording stopped.")
        send_telegram("⏹️ **Recording stopped.** Processing and uploading file...")
    except:
        if ffmpeg_process: ffmpeg_process.kill()
    finally:
        ffmpeg_process = None

# ============================================
# 🚀 MAIN BOT LOGIC
# ============================================
def run_bot():
    if not MEET_URL:
        log("❌ Error: MEET_URL is missing!")
        return

    send_telegram(f"🚀 **Runner Active**\n🔗 URL: `{MEET_URL}`\n\n*Waiting for manual join via RDP link. Once joined, click 'Start Recording' on Telegram.*")

    with sync_playwright() as p:
        # HIGH-STEALTH BROWSER CONFIGURATION
        browser = p.chromium.launch(headless=False, args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled", # Anti-bot
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
            "--window-size=1280,720",
            "--disable-dev-shm-usage",
            "--enable-unsafe-swiftshader", # For smooth rendering without GPU
            "--use-gl=angle",
            "--use-angle=swiftshader"
        ])

        # REALISTIC USER AGENT & FINGERPRINT
        context = browser.new_context(
            viewport={'width': 1280, 'height': 720},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            permissions=['camera', 'microphone'],
            locale="en-US",
            timezone_id="UTC"
        )

        # Apply Stealth to bypass detections
        page = context.new_page()
        stealth_sync(page)

        log(f"🌐 Navigating to meeting: {MEET_URL}")
        page.goto(MEET_URL, wait_until="networkidle", timeout=60000)

        # AUTO-JOIN LOGIC FOR GOOGLE MEET
        try:
            if "meet.google.com" in MEET_URL:
                log("🔍 Detecting Google Meet join buttons...")
                # Dismiss "Dismiss" or "Got it" buttons if any
                page.locator("button:has-text('Dismiss'), button:has-text('Got it')").click(timeout=5000).catch(lambda _: None)

                # Turn off mic and camera if possible (shortcuts: Ctrl+D, Ctrl+E)
                log("🔇 Turning off mic and camera...")
                page.keyboard.press("Control+d")
                page.keyboard.press("Control+e")
                time.sleep(2)

                # Click "Join now" or "Ask to join"
                join_button = page.locator("button:has-text('Join now'), button:has-text('Ask to join')")
                if join_button.is_visible():
                    log("✅ Clicking Join button...")
                    join_button.click()
                    send_telegram("🤖 **Auto-Join:** Clicked 'Join now/Ask to join' button.")
                else:
                    log("⚠️ Join button not found automatically. Please join via RDP.")
        except Exception as e:
            log(f"⚠️ Auto-join error: {e}")

        recording_active = False
        start_time = time.time()

        while time.time() - start_time < 21000: # ~6 hour session limit
            # Check for termination
            stop_val = get_command_flag("STOP_FLAG")
            if stop_val == "1":
                log("🛑 Termination signal received.")
                break

            # Recording Control
            rec_val = get_command_flag("REC_FLAG")
            if rec_val == "1" and not recording_active:
                start_recording()
                recording_active = True
            elif rec_val == "0" and recording_active:
                stop_recording()
                recording_active = False

            # Live View Screenshot
            view_val = get_command_flag("VIEW_FLAG")
            if view_val == "1":
                try:
                    path = "view.png"
                    page.screenshot(path=path)
                    with open(path, 'rb') as f:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={'chat_id': CHAT_ID, 'caption': f"📸 Live Screenshot - {datetime.now().strftime('%H:%M:%S')}"}, files={'photo': f})
                    os.remove(path)
                except: pass
                set_github_variable("VIEW_FLAG", "0")

            # Fullscreen Toggle
            full_val = get_command_flag("FULL_FLAG")
            if full_val == "1":
                try:
                    page.evaluate("document.documentElement.requestFullscreen()")
                    send_telegram("📺 Fullscreen mode enabled.")
                except: pass
                set_github_variable("FULL_FLAG", "0")

            # Prevent idle timeout (Move mouse randomly)
            if int(time.time()) % 60 < 5:
                try:
                    x, y = random.randint(100, 1000), random.randint(100, 600)
                    page.mouse.move(x, y)

                    # Auto-Stop if meeting ended (Google Meet specific)
                    if "meet.google.com" in MEET_URL:
                        if page.locator("text='You're the only one here'").is_visible() or \
                           page.locator("text='Meeting ended'").is_visible():
                            log("👋 Meeting seems to have ended. Shutting down...")
                            send_telegram("👋 **Meeting Ended:** Runner detected empty room or ended session.")
                            break
                except: pass

            time.sleep(5)

        if recording_active: stop_recording()
        browser.close()
        send_telegram("🏁 **Session Ended.** Runner shut down successfully.")

if __name__ == "__main__":
    run_bot()
