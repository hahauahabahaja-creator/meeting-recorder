import os
import time
import requests
import threading
import telebot
from flask import Flask
from datetime import datetime
import logging

# ==========================================
# ⚙️ LOGGING SETUP
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ==========================================
# ⚙️ SECRETS & CONFIGURATION
# ==========================================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") 
GITHUB_TOKEN = os.environ.get("PAT_TOKEN")
REPO_NAME = os.environ.get("GITHUB_REPO") 
WORKFLOW_NAME = "record.yml" 

# Optional Group ID lock
ALLOWED_GROUP_ID = os.environ.get("ALLOWED_GROUP_ID", "").strip()

if not all([BOT_TOKEN, GITHUB_TOKEN, REPO_NAME]):
    logger.warning("⚠️ Missing Environment Variables (TELEGRAM_BOT_TOKEN, PAT_TOKEN, GITHUB_REPO)!")

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)

# Global flags for direct Render command polling (bypasses GitHub variables)
stop_flag = "0"
view_flag = "0"
full_flag = "0"
rec_flag = "0"

# ==========================================
# 🔒 AUTHORIZATION CHECK
# ==========================================
def is_authorized(message):
    """Check if user/chat is authorized to use the bot"""
    if not ALLOWED_GROUP_ID:
        return True
        
    if str(message.chat.id) != str(ALLOWED_GROUP_ID):
        bot.reply_to(message, f"❌ Access Denied: Unauthorized chat/group (ID: {message.chat.id}).")
        return False
        
    # Check if the chat is a group and user is admin
    if message.chat.type in ['group', 'supergroup']:
        try:
            chat_admins = bot.get_chat_administrators(message.chat.id)
            admin_ids = [admin.user.id for admin in chat_admins]
            if message.from_user.id not in admin_ids:
                bot.reply_to(message, "⛔ **Access Denied!**\nOnly group admins can use this bot.", parse_mode="Markdown")
                return False
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            bot.reply_to(message, "⚠️ Error checking permissions. Please try again.")
            return False
            
    return True

# ==========================================
# 🛠️ GITHUB API INTERFACES
# ==========================================
def create_or_update_github_variable(var_name, value):
    """Creates a variable if it doesn't exist, or updates it if it does"""
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    try:
        res = requests.patch(url, json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        if res.status_code == 204:
            logger.info(f"✅ Variable {var_name} updated successfully to {value}")
            return True
        elif res.status_code == 404:
            create_url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables"
            create_res = requests.post(create_url, json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
            if create_res.status_code == 201:
                logger.info(f"✅ Variable {var_name} created successfully with value {value}")
                return True
            else:
                logger.warning(f"❌ Failed to create variable {var_name}: {create_res.status_code} - {create_res.text}")
        else:
            logger.warning(f"❌ Failed to update variable {var_name}: {res.status_code} - {res.text}")
    except Exception as e:
        logger.error(f"⚠️ Exception in create_or_update_github_variable: {e}")
    return False

def is_workflow_running():
    """Checks if the recorder workflow is currently running in GitHub Actions"""
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/runs?status=in_progress"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            total = data.get("total_count", 0)
            return total > 0
    except Exception as e:
        logger.error(f"Error checking workflow status: {e}")
    return False

def get_workflow_status():
    """Get active workflow run details"""
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/runs?status=in_progress"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            runs = res.json().get("workflow_runs", [])
            if runs:
                run = runs[0]
                return {
                    "id": run.get("id"),
                    "status": run.get("status"),
                    "created": run.get("created_at"),
                    "url": run.get("html_url")
                }
    except Exception as e:
        logger.error(f"Error getting workflow status: {e}")
    return None

# ==========================================
# 🤖 TELEGRAM BOT COMMANDS
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message):
        return
    
    user = message.from_user
    welcome_text = (
        "🛡️ **Multi-Platform Meeting Recorder Bot**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Welcome, {user.first_name}!\n\n"
        "**📋 Available Commands:**\n"
        "🚀 `/go <meeting_url>` - Start session & get RDP link\n"
        "⏺️ `/rec_on` - Start recording manually\n"
        "⏹️ `/rec_off` - Stop recording & upload\n"
        "🛑 `/off` - Full stop (Stop recording & close runner)\n"
        "📸 `/vew` - Take live screenshot\n"
        "📺 `/full` - Request fullscreen mode\n"
        "📊 `/status` - Check current status\n"
        "⚡ `/cancel` - Stop ongoing operation instantly\n\n"
        "**📌 Examples:**\n"
        "• `/go https://meet.google.com/abc-defg-hij`\n"
        "• `/go https://zoom.us/j/123456789?pwd=xxxx`\n"
        "• `/go https://teams.microsoft.com/l/meetup-join/...`"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def check_status(message):
    if not is_authorized(message):
        return
    
    status_msg = "🔍 **System Status**\n━━━━━━━━━━━━━━━━━━━━━\n"
    
    if is_workflow_running():
        details = get_workflow_status()
        status_msg += "✅ **Recording Session Active**\n"
        if details:
            status_msg += f"🆔 Run ID: `{details['id']}`\n"
            status_msg += f"⏰ Started: `{details['created']}`\n"
            status_msg += f"🔗 [View GitHub Action Run]({details['url']})\n"
    else:
        status_msg += "💤 **System Idle / Offline**\n"
        status_msg += "📌 Ready to start a new recording session."
    
    bot.reply_to(message, status_msg, parse_mode="Markdown")

@bot.message_handler(commands=['go'])
def start_recording(message):
    if not is_authorized(message):
        return
    
    try:
        parts = message.text.split()
        if len(parts) < 2:
            raise ValueError("No URL provided")
        meet_url = parts[1]
        
        # Ensure http prefix
        if not meet_url.startswith(('http://', 'https://')):
            meet_url = 'https://' + meet_url
            
        # Basic validation
        valid_domains = ['meet.google.com', 'zoom.us', 'teams.microsoft.com', 'teams.live.com']
        if not any(domain in meet_url for domain in valid_domains):
            bot.reply_to(message, "⚠️ **Unsupported Meeting Platform**\nPlease provide a Google Meet, Zoom, or Teams link.", parse_mode="Markdown")
            return
            
    except Exception:
        bot.reply_to(
            message, 
            "⚠️ **Invalid Command Format**\nPlease use:\n`/go <meeting_url>`",
            parse_mode="Markdown"
        )
        return

    # Check if a workflow is already running
    if is_workflow_running():
        details = get_workflow_status()
        status_msg = (
            "⚠️ **Recording Session Active!**\n━━━━━━━━━━━━━━━━━━━━━\n"
            "A recording is currently in progress.\n\n"
            "**Options:**\n"
            "🔄 Use `/off` to stop the current recording\n"
            "📊 Use `/status` for more details\n"
            "⏳ Please wait for current run to finish."
        )
        if details:
            status_msg += f"\n\n🆔 Run ID: `{details['id']}`"
        
        bot.reply_to(message, status_msg, parse_mode="Markdown")
        return

    # Start recording process
    progress_msg = bot.reply_to(
        message, 
        f"⏳ **Initializing Cloud Recorder**\n━━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 Target URL: `{meet_url}`\n"
        f"⚙️ Allocating virtual runner resources...\n"
        f"⏱️ Please wait 30-60 seconds for startup.",
        parse_mode="Markdown"
    )
    
    # Initialize flags
    global stop_flag, view_flag, full_flag, rec_flag
    stop_flag = "0"
    view_flag = "0"
    full_flag = "0"
    rec_flag = "0"

    create_or_update_github_variable("STOP_FLAG", "0")
    create_or_update_github_variable("VIEW_FLAG", "0")
    create_or_update_github_variable("FULL_FLAG", "0")
    create_or_update_github_variable("REC_FLAG", "0")

    # Dispatch GitHub Actions Workflow
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/dispatches"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json"
    }
    
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
    data = {
        "ref": "main",
        "inputs": {
            "meet_url": meet_url,
            "render_url": render_url
        }
    }
    
    try:
        res = requests.post(url, json=data, headers=headers, timeout=30)
        
        if res.status_code == 204:
            bot.edit_message_text(
                f"✅ **Recording Started Successfully**\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 URL: `{meet_url}`\n"
                f"🟢 Status: Active\n"
                f"⏱️ Max duration: 5 hours\n\n"
                f"**📋 Controls:**\n"
                f"🛑 `/off` - Stop recording\n"
                f"📸 `/vew` - Take live screenshot\n"
                f"📺 `/full` - Toggle full screen\n"
                f"📊 `/status` - Check runner status",
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                f"❌ **GitHub API Error**\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"Failed to trigger GitHub Actions runner.\n"
                f"Status Code: {res.status_code}\n"
                f"Response: `{res.text[:150]}`",
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error starting workflow: {e}")
        bot.edit_message_text(
            f"❌ **Connection Error**\n━━━━━━━━━━━━━━━━━━━━━\n"
            f"Unable to connect to GitHub Actions REST API.\n"
            f"Please verify your credentials and try again.",
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['off'])
def stop_recording(message):
    if not is_authorized(message):
        return
    
    if not is_workflow_running():
        bot.reply_to(
            message,
            "💤 **No Active Recording**\nThere is no recording session running currently.",
            parse_mode="Markdown"
        )
        return
    
    progress_msg = bot.reply_to(
        message,
        "🛑 **Stopping Recording**\n━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Sending halt command to runner...\n"
        "⏱️ Finalizing media fragments & uploading to Telegram (takes up to 2-3 mins)...",
        parse_mode="Markdown"
    )
    
    global stop_flag
    stop_flag = "1"
    create_or_update_github_variable("STOP_FLAG", "1")
    
    time.sleep(5)
    bot.edit_message_text(
        "✅ **Stop Signal Sent Successfully**\n━━━━━━━━━━━━━━━━━━━━━\n"
        "🔄 Processing video segment files.\n"
        "📥 You will receive the files directly here shortly.",
        chat_id=message.chat.id,
        message_id=progress_msg.message_id,
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['vew'])
def live_view(message):
    if not is_authorized(message):
        return
        
    if not is_workflow_running():
        bot.reply_to(
            message,
            "💤 **No Active Recording**\nCannot capture screenshot without an active session.",
            parse_mode="Markdown"
        )
        return
        
    bot.reply_to(
        message,
        "📸 **Screenshot Capture Signal Sent**\n━━━━━━━━━━━━━━━━━━━━━\n"
        "⏳ Taking screenshot on runner...\n"
        "📤 You will receive the photo here in a few seconds.",
        parse_mode="Markdown"
    )
    global view_flag
    view_flag = "1"
    create_or_update_github_variable("VIEW_FLAG", "1")

@bot.message_handler(commands=['full'])
def full_screen(message):
    if not is_authorized(message):
        return
        
    if not is_workflow_running():
        bot.reply_to(
            message,
            "💤 **No Active Recording**\nCannot change display mode without an active session.",
            parse_mode="Markdown"
        )
        return
        
    bot.reply_to(
        message,
        "📺 **Fullscreen Command Sent**\n━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Requesting fullscreen mode on the runner page.",
        parse_mode="Markdown"
    )
    global full_flag
    full_flag = "1"
    create_or_update_github_variable("FULL_FLAG", "1")

@bot.message_handler(commands=['cancel'])
def cancel_operation(message):
    if not is_authorized(message):
        return
        
    if is_workflow_running():
        bot.reply_to(
            message,
            "⚡ **Emergency Cancel**\n━━━━━━━━━━━━━━━━━━━━━\n"
            "🛑 Halting all operations and shutting down runner...",
            parse_mode="Markdown"
        )
        global stop_flag
        stop_flag = "1"
        create_or_update_github_variable("STOP_FLAG", "1")
    else:
        bot.reply_to(
            message,
            "💤 **No Operation Running**\nNothing to cancel.",
            parse_mode="Markdown"
        )

# ==========================================
# 🌐 FLASK WEB SERVER
# ==========================================

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Meeting Recorder Controller</title>
        <style>
            body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0c0f12; color: #e2ebf0; text-align: center; padding: 50px; margin: 0; }
            .status { background: #151b22; padding: 40px; border-radius: 12px; max-width: 600px; margin: 50px auto; box-shadow: 0 4px 20px rgba(0,0,0,0.4); border: 1px solid #30363d; }
            .online { color: #58a6ff; font-size: 28px; font-weight: bold; margin: 20px 0; }
            .detail { color: #8b949e; margin: 12px 0; font-size: 16px; }
            h1 { color: #f0f6fc; margin-bottom: 5px; }
        </style>
    </head>
    <body>
        <div class="status">
            <h1>🛡️ Cloud Recorder Controller</h1>
            <div class="online">🟢 Web Interface Online</div>
            <div class="detail">Telegram controller is active and polling.</div>
            <div class="detail">🎯 Control is managed exclusively via the authorized Telegram chat.</div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "recording": is_workflow_running(),
        "authorized_group": ALLOWED_GROUP_ID or "all"
    }

@bot.message_handler(commands=['rec_on'])
def start_rec_command(message):
    if not is_authorized(message):
        return
    if not is_workflow_running():
        bot.reply_to(message, "💤 **No Active Session**\nStart a session with `/go` first.", parse_mode="Markdown")
        return

    global rec_flag
    rec_flag = "1"
    create_or_update_github_variable("REC_FLAG", "1")
    bot.reply_to(message, "⏺️ **Recording Signal Sent**\nFFmpeg is starting and RDP will be disabled for performance.", parse_mode="Markdown")

@bot.message_handler(commands=['rec_off'])
def stop_rec_command(message):
    if not is_authorized(message):
        return
    if not is_workflow_running():
        bot.reply_to(message, "💤 **No Active Session**", parse_mode="Markdown")
        return

    global rec_flag
    rec_flag = "0"
    create_or_update_github_variable("REC_FLAG", "0")
    bot.reply_to(message, "⏹️ **Stop Recording Signal Sent**\nFinalizing video file...", parse_mode="Markdown")

@app.route('/api/command')
def get_command():
    global stop_flag, view_flag, full_flag, rec_flag
    res = {
        "stop": stop_flag,
        "view": view_flag,
        "full": full_flag,
        "rec": rec_flag
    }
    # Reset transient flags after they are read by the runner
    view_flag = "0"
    full_flag = "0"
    return res

# ==========================================
# 🚀 BOT RUNNER
# ==========================================

def run_bot_polling():
    while True:
        try:
            logger.info("🤖 Starting Telegram Bot polling...")
            bot.polling(none_stop=True, timeout=60, interval=5)
        except Exception as e:
            logger.error(f"Bot polling exception occurred: {e}")
            time.sleep(10)

if __name__ == "__main__":
    logger.info("🚀 Booting up Cloud Recorder Controller...")
    
    if bot:
        threading.Thread(target=run_bot_polling, daemon=True).start()
    else:
        logger.error("❌ TELEGRAM_BOT_TOKEN not provided, bot will not poll!")
        
    port = int(os.environ.get("PORT", 10000))
    logger.info(f"🌐 Running Flask status page on port {port}")
    app.run(host="0.0.0.0", port=port)
