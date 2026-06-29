import os
import time
import requests
import threading
import telebot
from flask import Flask
from datetime import datetime
import logging
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

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

def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("📊 Status", callback_data="cb_status"),
               InlineKeyboardButton("📸 Screenshot", callback_data="cb_vew"))
    markup.row(InlineKeyboardButton("⏺️ Start Rec", callback_data="cb_rec_on"),
               InlineKeyboardButton("⏹️ Stop Rec", callback_data="cb_rec_off"))
    markup.row(InlineKeyboardButton("🛑 Stop Bot", callback_data="cb_off"),
               InlineKeyboardButton("📺 Fullscreen", callback_data="cb_full"))
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message):
        return
    
    user = message.from_user
    welcome_text = (
        "🛡️ **Advanced Meeting Recorder Bot**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Welcome, {user.first_name}!\n\n"
        "**🚀 Quick Start:**\n"
        "Type `/go <url>` to launch the browser.\n\n"
        "**📋 Interactive Controls:**\n"
        "Use the buttons below to control the bot once it's running."
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

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
    
    bot.reply_to(message, status_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

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
        
        bot.reply_to(message, status_msg, parse_mode="Markdown", reply_markup=get_main_keyboard())
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
                f"✅ **Runner Started Successfully**\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 URL: `{meet_url}`\n"
                f"🟢 Status: Initializing...\n\n"
                f"**You will receive the RDP link shortly.**",
                chat_id=message.chat.id,
                message_id=progress_msg.message_id,
                parse_mode="Markdown",
                reply_markup=get_main_keyboard()
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
            f"Unable to connect to GitHub Actions REST API.",
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            parse_mode="Markdown"
        )

@bot.message_handler(commands=['off'])
def stop_recording_cmd(message):
    if not is_authorized(message):
        return
    handle_stop_bot(message.chat.id)

@bot.message_handler(commands=['vew'])
def live_view_cmd(message):
    if not is_authorized(message):
        return
    handle_live_view(message.chat.id)

@bot.message_handler(commands=['full'])
def full_screen_cmd(message):
    if not is_authorized(message):
        return
    handle_full_screen(message.chat.id)

@bot.message_handler(commands=['rec_on', 'record'])
def start_rec_cmd(message):
    if not is_authorized(message):
        return
    handle_rec_on(message.chat.id)

@bot.message_handler(commands=['rec_off'])
def stop_rec_cmd(message):
    if not is_authorized(message):
        return
    handle_rec_off(message.chat.id)

@bot.message_handler(commands=['cancel'])
def cancel_cmd(message):
    if not is_authorized(message):
        return
    handle_stop_bot(message.chat.id)

# ==========================================
# 🛠️ CALLBACK HANDLERS
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data.startswith('cb_'))
def callback_handler(call):
    if not is_authorized(call.message):
        return
    
    action = call.data.replace('cb_', '')
    chat_id = call.message.chat.id
    
    if action == "status":
        check_status(call.message)
    elif action == "vew":
        handle_live_view(chat_id)
    elif action == "rec_on":
        handle_rec_on(chat_id)
    elif action == "rec_off":
        handle_rec_off(chat_id)
    elif action == "off":
        handle_stop_bot(chat_id)
    elif action == "full":
        handle_full_screen(chat_id)
    
    bot.answer_callback_query(call.id)

# ==========================================
# ⚙️ LOGIC WRAPPERS
# ==========================================

def handle_live_view(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **No Active Session**", parse_mode="Markdown")
        return
    bot.send_message(chat_id, "📸 **Capturing Live View...**", parse_mode="Markdown")
    global view_flag
    view_flag = "1"
    create_or_update_github_variable("VIEW_FLAG", "1")

def handle_rec_on(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **No Active Session**", parse_mode="Markdown")
        return
    global rec_flag
    rec_flag = "1"
    create_or_update_github_variable("REC_FLAG", "1")
    bot.send_message(chat_id, "⏺️ **Recording Signal Sent.** RDP will be closed for speed.", parse_mode="Markdown")

def handle_rec_off(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **No Active Session**", parse_mode="Markdown")
        return
    global rec_flag
    rec_flag = "0"
    create_or_update_github_variable("REC_FLAG", "0")
    bot.send_message(chat_id, "⏹️ **Stopping Recording...** Finalizing file.", parse_mode="Markdown")

def handle_stop_bot(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **No Active Session**", parse_mode="Markdown")
        return
    bot.send_message(chat_id, "🛑 **Stopping Bot & Runner...**", parse_mode="Markdown")
    global stop_flag
    stop_flag = "1"
    create_or_update_github_variable("STOP_FLAG", "1")

def handle_full_screen(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **No Active Session**", parse_mode="Markdown")
        return
    bot.send_message(chat_id, "📺 **Requesting Fullscreen...**", parse_mode="Markdown")
    global full_flag
    full_flag = "1"
    create_or_update_github_variable("FULL_FLAG", "1")

# ==========================================
# 🌐 FLASK WEB SERVER
# ==========================================

@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Meeting Recorder | Dashboard</title>
        <style>
            :root {
                --bg: #0d1117;
                --panel: #161b22;
                --border: #30363d;
                --text: #c9d1d9;
                --accent: #58a6ff;
                --green: #238636;
            }
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }
            .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 40px; width: 100%; max-width: 450px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
            h1 { font-size: 24px; margin-bottom: 8px; color: #fff; }
            p { color: #8b949e; margin-bottom: 24px; }
            .status-badge { display: inline-flex; align-items: center; background: rgba(35, 134, 54, 0.15); color: #3fb950; padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 14px; border: 1px solid rgba(63, 185, 80, 0.3); }
            .footer { margin-top: 30px; font-size: 12px; color: #484f58; }
            .dot { height: 8px; width: 8px; background-color: #3fb950; border-radius: 50%; display: inline-block; margin-right: 8px; animation: pulse 2s infinite; }
            @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.4; } 100% { opacity: 1; } }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>🛡️ Bot Controller</h1>
            <p>Cloud Meeting Recorder is active</p>
            <div class="status-badge">
                <span class="dot"></span> Web Interface Online
            </div>
            <div class="footer">
                Managed via Authorized Telegram Account
            </div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health_check():
    return {
        "status": "online",
        "timestamp": datetime.now().isoformat(),
        "recording": is_workflow_running()
    }

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
