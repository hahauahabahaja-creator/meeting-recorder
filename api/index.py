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
ALLOWED_GROUP_ID = os.environ.get("ALLOWED_GROUP_ID", "").strip()

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None
app = Flask(__name__)

# Global flags
stop_flag = "0"
view_flag = "0"
full_flag = "0"
rec_flag = "0"

def is_authorized(message):
    if not ALLOWED_GROUP_ID: return True
    return str(message.chat.id) == str(ALLOWED_GROUP_ID)

def create_or_update_github_variable(var_name, value):
    url = f"https://api.github.com/repos/{REPO_NAME}/actions/variables/{var_name}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.patch(url, json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        if res.status_code == 404:
            requests.post(f"https://api.github.com/repos/{REPO_NAME}/actions/variables", json={"name": var_name, "value": str(value)}, headers=headers, timeout=10)
        return True
    except: return False

def get_repo_visibility():
    url = f"https://api.github.com/repos/{REPO_NAME}"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json().get("visibility", "private")
    except: pass
    return "private"

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
        "💀 **GHOST RECORDER PRO**\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "Advanced Meeting Control Interface Active.\n\n"
        "🚀 `/go <url>` - Deploy Bot"
    )
    bot.send_message(message.chat.id, welcome_text, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['status'])
def status_cmd(message):
    if not is_authorized(message): return

    visibility = get_repo_visibility()

    msg = "📊 **GHOST SYSTEM STATUS**\n━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"🟢 **Runner:** {'ACTIVE' if is_workflow_running() else 'IDLE'}\n"
    msg += f"📂 **Repo Mode:** `{visibility.upper()}`\n"

    if visibility == "public":
        msg += "🔋 **Usage Limit:** `UNLIMITED (Free)`\n"
        msg += "✨ *Public repo mode enables infinite recording time.*"
    else:
        msg += "🔋 **Usage Limit:** `2,000 mins/month`\n"
        msg += "⚠️ *Private repo has a 2000 minute cap.*"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

@bot.message_handler(commands=['go'])
def start_recording(message):
    if not is_authorized(message): return
    try:
        meet_url = message.text.split()[1]
    except:
        bot.reply_to(message, "⚠️ Usage: `/go <url>`")
        return

    if is_workflow_running():
        bot.reply_to(message, "⚠️ **Session Active.**")
        return

    progress_msg = bot.reply_to(message, "⏳ **Deploying Ghost Runner...**", parse_mode="Markdown")
    
    global stop_flag, view_flag, full_flag, rec_flag
    stop_flag, view_flag, full_flag, rec_flag = "0", "0", "0", "0"
    for f in ["STOP_FLAG", "VIEW_FLAG", "FULL_FLAG", "REC_FLAG"]:
        create_or_update_github_variable(f, "0")

    url = f"https://api.github.com/repos/{REPO_NAME}/actions/workflows/{WORKFLOW_NAME}/dispatches"
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}", "Accept": "application/vnd.github+json"}
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()

    try:
        res = requests.post(url, json={"ref": "main", "inputs": {"meet_url": meet_url, "render_url": render_url}}, headers=headers, timeout=30)
        if res.status_code == 204:
            bot.edit_message_text(
                f"✅ **Runner Active!**\n━━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 **Target:** `{meet_url}`\n"
                f"⏱️ **Started:** {datetime.now().strftime('%H:%M:%S')}\n\n"
                f"Instructions sent. Waiting for RDP...",
                chat_id=message.chat.id, message_id=progress_msg.message_id,
                parse_mode="Markdown", reply_markup=get_main_keyboard()
            )
        else:
            bot.edit_message_text(f"❌ **GitHub Error:** {res.status_code}", chat_id=message.chat.id, message_id=progress_msg.message_id)
    except:
        bot.edit_message_text("❌ **Failed.**", chat_id=message.chat.id, message_id=progress_msg.message_id)

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
    if not is_workflow_running(): return
    global view_flag
    view_flag = "1"
    create_or_update_github_variable("VIEW_FLAG", "1")
    bot.send_message(chat_id, "📸 **Capturing...**")

def handle_rec_on(chat_id):
    if not is_workflow_running(): return
    global rec_flag
    rec_flag = "1"
    create_or_update_github_variable("REC_FLAG", "1")
    bot.send_message(chat_id, "⏺️ **Recording Started.**")

def handle_rec_off(chat_id):
    if not is_workflow_running(): return
    global rec_flag
    rec_flag = "0"
    create_or_update_github_variable("REC_FLAG", "0")
    bot.send_message(chat_id, "⏹️ **Recording Stopped.**")

def handle_stop_bot(chat_id):
    if not is_workflow_running(): return
    global stop_flag
    stop_flag = "1"
    create_or_update_github_variable("STOP_FLAG", "1")
    bot.send_message(chat_id, "🛑 **Terminating Session.**")

def handle_full_screen(chat_id):
    if not is_workflow_running(): return
    global full_flag
    full_flag = "1"
    create_or_update_github_variable("FULL_FLAG", "1")
    bot.send_message(chat_id, "📺 **Fullscreen.**")

@app.route('/api/command')
def get_command():
    global stop_flag, view_flag, full_flag, rec_flag
    res = {"stop": stop_flag, "view": view_flag, "full": full_flag, "rec": rec_flag}
    view_flag, full_flag = "0", "0"
    return res

if __name__ == "__main__":
    if bot: threading.Thread(target=lambda: bot.polling(none_stop=True), daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
