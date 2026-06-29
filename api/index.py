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

# Global flags for direct Render command polling
stop_flag = "0"
view_flag = "0"
full_flag = "0"
rec_flag = "0"

# ==========================================
# 🔒 AUTHORIZATION CHECK
# ==========================================
def is_authorized(message):
    if not ALLOWED_GROUP_ID: return True
    if str(message.chat.id) != str(ALLOWED_GROUP_ID):
        bot.reply_to(message, f"❌ Access Denied.")
        return False
    return True

# ==========================================
# 🛠️ GITHUB API INTERFACES
# ==========================================
def create_or_update_github_variable(var_name, value):
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.patch(url, json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        if res.status_code == 404:
            requests.post(f"https://api.github.com/repos/{REPO_NAME}/actions/variables", json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        return True
    except: return False

def is_workflow_running():
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/runs?status=in_progress"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        return res.json().get("total_count", 0) > 0
    except: return False

# ==========================================
# 🤖 TELEGRAM BOT UI
# ==========================================

def get_main_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(InlineKeyboardButton("⏺️ Start Recording", callback_data="cb_rec_on"))
    markup.row(InlineKeyboardButton("📸 Live View", callback_data="cb_vew"),
               InlineKeyboardButton("📺 Fullscreen", callback_data="cb_full"))
    markup.row(InlineKeyboardButton("⏹️ Stop Recording", callback_data="cb_rec_off"))
    markup.row(InlineKeyboardButton("📊 System Status", callback_data="cb_status"))
    markup.row(InlineKeyboardButton("🛑 Terminate Runner", callback_data="cb_off"))
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    if not is_authorized(message): return
    welcome_text = (
        "💎 **PREMIUM CLOUD RECORDER**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome! I am your advanced meeting assistant.\n\n"
        "**Quick Launch:**\n"
        "🚀 Use `/go <meeting_url>` to start.\n\n"
        "**Manual Control:**\n"
        "Use the interactive dashboard below to manage your session."
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['go'])
def start_recording(message):
    if not is_authorized(message): return
    
    try:
        parts = message.text.split()
        if len(parts) < 2: raise ValueError()
        meet_url = parts[1]
    except:
        bot.reply_to(message, "⚠️ Usage: `/go <url>`")
        return

    if is_workflow_running():
        bot.reply_to(message, "⚠️ **A session is already active.** Please stop it first.")
        return

    progress_msg = bot.reply_to(message, "⏳ **Initializing Runner...**\n*Allocating cloud resources and setting up RDP.*", parse_mode="Markdown")
    
    # Reset Flags
    global stop_flag, view_flag, full_flag, rec_flag
    stop_flag, view_flag, full_flag, rec_flag = "0", "0", "0", "0"
    for f in ["STOP_FLAG", "VIEW_FLAG", "FULL_FLAG", "REC_FLAG"]:
        create_or_update_github_variable(f, "0")

    # Trigger Action
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/dispatches"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()

    try:
        res = requests.post(url, json={"ref": "main", "inputs": {"meet_url": meet_url, "render_url": render_url}}, headers=headers, timeout=30)
        if res.status_code == 204:
            bot.edit_message_text(
                f"✅ **Runner Deployed Successfully!**\n"
                f"━━━━━━━━━━━━━━━━━━━━━\n"
                f"🔗 **Target:** `{meet_url}`\n"
                f"🕒 **Time:** {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"**Instructions:**\n"
                f"1. Wait for the **RDP Link** (approx. 40s).\n"
                f"2. Open it & join the meeting manually.\n"
                f"3. Return here & click **Start Recording**.",
                chat_id=message.chat.id, message_id=progress_msg.message_id,
                parse_mode="Markdown", reply_markup=get_main_keyboard()
            )
        else:
            bot.edit_message_text(f"❌ **GitHub Error:** {res.status_code}", chat_id=message.chat.id, message_id=progress_msg.message_id)
    except:
        bot.edit_message_text("❌ **Connection Failed.**", chat_id=message.chat.id, message_id=progress_msg.message_id)

@bot.message_handler(commands=['status'])
def status_cmd(message):
    if not is_authorized(message): return
    msg = "🔍 **System Status**\n━━━━━━━━━━━━━━━━━━━━━\n"
    if is_workflow_running():
        msg += "🟢 **Runner:** Active & Online\n⏺️ **Rec Mode:** Managed by Dashboard"
    else:
        msg += "💤 **Runner:** Idle / Offline"
    bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

# Aliases for manual typing
@bot.message_handler(commands=['rec_on', 'record', 'recod'])
def rec_on_cmd(message):
    if not is_authorized(message): return
    handle_rec_on(message.chat.id)

@bot.message_handler(commands=['rec_off'])
def rec_off_cmd(message):
    if not is_authorized(message): return
    handle_rec_off(message.chat.id)

@bot.message_handler(commands=['off', 'stop'])
def stop_cmd(message):
    if not is_authorized(message): return
    handle_stop_bot(message.chat.id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('cb_'))
def callback_handler(call):
    if not is_authorized(call.message): return
    action = call.data.replace('cb_', '')
    if action == "status": status_cmd(call.message)
    elif action == "vew": handle_live_view(call.message.chat.id)
    elif action == "rec_on": handle_rec_on(call.message.chat.id)
    elif action == "rec_off": handle_rec_off(call.message.chat.id)
    elif action == "off": handle_stop_bot(call.message.chat.id)
    elif action == "full": handle_full_screen(call.message.chat.id)
    bot.answer_callback_query(call.id)

def handle_live_view(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **Offline**")
        return
    bot.send_message(chat_id, "📸 **Signal Sent:** Capturing Live View...")
    global view_flag
    view_flag = "1"
    create_or_update_github_variable("VIEW_FLAG", "1")

def handle_rec_on(chat_id):
    if not is_workflow_running():
        bot.send_message(chat_id, "💤 **Offline**")
        return
    global rec_flag
    rec_flag = "1"
    create_or_update_github_variable("REC_FLAG", "1")
    bot.send_message(chat_id, "⏺️ **Recording Started!**\n*RDP optimized for performance.*", parse_mode="Markdown")

def handle_rec_off(chat_id):
    if not is_workflow_running(): return
    global rec_flag
    rec_flag = "0"
    create_or_update_github_variable("REC_FLAG", "0")
    bot.send_message(chat_id, "⏹️ **Recording Stopped.** Finalizing...")

def handle_stop_bot(chat_id):
    if not is_workflow_running(): return
    bot.send_message(chat_id, "🛑 **Terminating Session...**")
    global stop_flag
    stop_flag = "1"
    create_or_update_github_variable("STOP_FLAG", "1")

def handle_full_screen(chat_id):
    if not is_workflow_running(): return
    bot.send_message(chat_id, "📺 **Fullscreen Requested.**")
    global full_flag
    full_flag = "1"
    create_or_update_github_variable("FULL_FLAG", "1")

@app.route('/')
def index():
    return "<h1>Premium Recorder Controller is Active</h1>"

@app.route('/api/command')
def get_command():
    global stop_flag, view_flag, full_flag, rec_flag
    res = {"stop": stop_flag, "view": view_flag, "full": full_flag, "rec": rec_flag}
    view_flag, full_flag = "0", "0"
    return res

def run_bot_polling():
    while True:
        try:
            bot.polling(none_stop=True, timeout=60, interval=5)
        except Exception as e:
            logger.error(f"Error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    if bot: threading.Thread(target=run_bot_polling, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
