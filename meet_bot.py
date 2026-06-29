import os
import time
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
BOT_NAME = os.environ.get("BOT_NAME", "Meeting Bot")

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
        # Optimized for quality and low lag
        cmd = [
            "ffmpeg", "-y", "-thread_queue_size", "4096",
            "-f", "x11grab", "-video_size", "1366x768", "-framerate", "30", "-i", ":99",
            "-f", "pulse", "-i", "default",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "output.mp4"
        ]
        ffmpeg_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log(f"✅ Recording started (PID: {ffmpeg_process.pid})")

        # Kill RDP for performance
        log("🧹 Disabling RDP for performance...")
        subprocess.run("pkill -f websockify", shell=True)
        subprocess.run("pkill -f x11vnc", shell=True)
        send_telegram("⏺️ **Recording started.** RDP disabled to ensure smooth video.")
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
        send_telegram("⏹️ **Recording stopped.** Processing file...")
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

    send_telegram(f"🚀 **Runner Active**\n🔗 Meeting: `{MEET_URL}`\n\n*Waiting for your manual join via RDP or /record command...*")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=[
            "--no-sandbox", "--disable-setuid-sandbox", "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream", "--window-size=1366,768"
        ])
        context = browser.new_context(viewport={'width': 1366, 'height': 768}, permissions=['camera', 'microphone'])
        stealth_sync(context.new_page()) # Just to apply stealth to the context
        page = context.new_page()
        
        log(f"🌐 Navigating to: {MEET_URL}")
        page.goto(MEET_URL, timeout=60000)

        recording_active = False
        start_time = time.time()

        while time.time() - start_time < 18000: # 5 hour limit
            # Check Commands
            stop_val = get_command_flag("STOP_FLAG")
            if stop_val == "1":
                log("🛑 Stop command received.")
                break

            rec_val = get_command_flag("REC_FLAG")
            if rec_val == "1" and not recording_active:
                start_recording()
                recording_active = True
            elif rec_val == "0" and recording_active:
                stop_recording()
                recording_active = False

            view_val = get_command_flag("VIEW_FLAG")
            if view_val == "1":
                try:
                    path = "view.png"
                    page.screenshot(path=path)
                    with open(path, 'rb') as f:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", data={'chat_id': CHAT_ID}, files={'photo': f})
                    os.remove(path)
                except: pass
                set_github_variable("VIEW_FLAG", "0")

            full_val = get_command_flag("FULL_FLAG")
            if full_val == "1":
                try:
                    page.evaluate("document.documentElement.requestFullscreen()")
                    send_telegram("📺 Fullscreen requested.")
                except: pass
                set_github_variable("FULL_FLAG", "0")

            time.sleep(5)

        if recording_active: stop_recording()
        browser.close()
        send_telegram("🏁 **Session Ended.** Runner closing.")

if __name__ == "__main__":
    run_bot()
