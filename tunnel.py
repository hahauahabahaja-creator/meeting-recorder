import os
import re
import time
import requests
import subprocess
import sys

def send_telegram(bot_token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

def get_ngrok_url():
    try:
        res = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        if res.status_code == 200:
            tunnels = res.json().get("tunnels", [])
            if tunnels:
                return tunnels[0].get("public_url")
    except:
        pass
    return None

def start_tunnel():
    bot_token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")
    vnc_pass = os.environ.get("VNC_PASS", "")
    ngrok_token = os.environ.get("NGROK_AUTH_TOKEN", "").strip()

    if not bot_token or not chat_id:
        print("❌ Error: BOT_TOKEN or CHAT_ID missing.")
        return

    final_url = None

    # 1. Try Ngrok if token is provided
    if ngrok_token:
        print("📡 Starting Ngrok tunnel...")
        try:
            # Check if ngrok is already installed, if not, install it
            subprocess.run("ngrok version", shell=True, capture_output=True)
            if subprocess.run("ngrok version", shell=True).returncode != 0:
                subprocess.run("curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null && echo \"deb https://ngrok-agent.s3.amazonaws.com buster main\" | sudo tee /etc/apt/sources.list.d/ngrok.list && sudo apt-get update && sudo apt-get install -y ngrok", shell=True)

            subprocess.run(f"ngrok config add-authtoken {ngrok_token}", shell=True)
            subprocess.Popen("ngrok http 6080 --log=stdout > tunnel_ngrok.log 2>&1", shell=True)

            for _ in range(10):
                time.sleep(2)
                final_url = get_ngrok_url()
                if final_url:
                    print(f"✅ Ngrok tunnel established: {final_url}")
                    break
        except Exception as e:
            print(f"⚠️ Ngrok failed: {e}")

    # 2. Try Fallbacks if Ngrok failed or was not provided
    if not final_url:
        fallbacks = [
            {"name": "Serveo", "cmd": "ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -R 80:localhost:6080 serveo.net", "pattern": r"https?://[a-zA-Z0-9.-]+\.serveo\.net", "log": "tunnel_serveo.log"},
            {"name": "Pinggy", "cmd": "ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60 -p 443 -R 0:localhost:6080 a.pinggy.io", "pattern": r"https?://[a-zA-Z0-9.-]+\.pinggy\.(?:link|io)", "log": "tunnel_pinggy.log"},
            {"name": "Localhost.run", "cmd": "ssh -o StrictHostKeyChecking=no -R 80:localhost:6080 nokey@localhost.run", "pattern": r"https?://[a-zA-Z0-9.-]+\.(?:lhr\.life|localhost\.run|lhr\.rocks)", "log": "tunnel_lhr.log"}
        ]

        for fb in fallbacks:
            print(f"📡 Starting {fb['name']} tunnel...")
            proc = subprocess.Popen(f"{fb['cmd']} > {fb['log']} 2>&1", shell=True)

            for _ in range(5):
                time.sleep(3)
                if os.path.exists(fb['log']):
                    with open(fb['log'], "r") as f:
                        log_content = f.read()
                    match = re.search(fb['pattern'], log_content)
                    if match:
                        final_url = match.group(0)
                        print(f"✅ {fb['name']} tunnel established: {final_url}")
                        break

            if final_url:
                break
            else:
                print(f"⚠️ {fb['name']} failed. Killing process...")
                proc.terminate()
                subprocess.run(f"pkill -f '{fb['name'].lower()}'", shell=True)

    # 3. Send to Telegram
    if final_url:
        vnc_url = f"{final_url}/vnc.html?autoconnect=true&resize=scale&password={vnc_pass}"
        msg = (
            "🖥️ **Interactive RDP Access**\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "Join the meeting manually using the link below:\n\n"
            f"🔗 [Open Interactive RDP]({vnc_url})\n\n"
            "**Steps:**\n"
            "1. Open the link above\n"
            "2. Join the meeting in the browser\n"
            "3. Once joined, return to Telegram and use `/record` to start recording.\n\n"
            "⚠️ *Note: RDP will be closed automatically when recording starts to save resources.*"
        )
        send_telegram(bot_token, chat_id, msg)
    else:
        send_telegram(bot_token, chat_id, "❌ **Tunnel Error:** Failed to establish any public tunnel.")

if __name__ == "__main__":
    start_tunnel()
