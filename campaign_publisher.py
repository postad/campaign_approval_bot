import os
import json
import time
import threading
import gspread
from google.oauth2.service_account import Credentials
from telebot import TeleBot, types
from urllib.parse import urlparse

# === CONFIG ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
APPROVER_ID = int(os.getenv("APPROVER_ID"))  # Telegram user ID of the approver
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# === INIT GOOGLE SHEETS ===
creds_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).sheet1

# === INIT TELEGRAM BOT ===
bot = TeleBot(BOT_TOKEN)

# === CORE FUNCTIONS ===

def get_pending_post():
    data = sheet.get_all_records()
    for i, row in enumerate(data, start=2):  # Start at row 2 because of headers
        if row.get("status", "").lower() == "pending":
            return i, row
    return None, None

def extract_url_from_text(text):
    words = text.split()
    for word in reversed(words):  # Look from end
        if urlparse(word).scheme in ["http", "https"]:
            return word
    return ""

def send_for_approval(row_num, post_data):
    try:
        post_id = post_data["post_id"]
        text = post_data["text"]
        file_id = post_data.get("media_id", "")
        url = extract_url_from_text(text)

        if url:
            text = text.replace(url, "") + f"\n{url}"

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{row_num}_{post_id}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"reject_{row_num}_{post_id}")
        )

        if file_id:
            bot.send_photo(APPROVER_ID, file_id, caption=text, reply_markup=markup)
        else:
            bot.send_message(APPROVER_ID, text, reply_markup=markup)

        print(f"📨 Sending post {post_id} to approver {APPROVER_ID}")
        # Mark as sent
        sheet.update_cell(row_num, get_col_index("status"), "sent")
    except Exception as e:
        print(f"⚠️ Error sending for approval: {e}")

def get_col_index(col_name):
    headers = sheet.row_values(1)
    return headers.index(col_name) + 1

def publish_post(row_data):
    channel_username = row_data["channel_username"]
    text = row_data["text"]
    file_id = row_data.get("media_id", "")
    url = extract_url_from_text(text)

    if url:
        text = text.replace(url, "") + f"\n{url}"

    try:
        if not channel_username.startswith("@"):
            channel_username = f"@{channel_username}"

        if file_id:
            bot.send_photo(channel_username, file_id, caption=text)
        else:
            bot.send_message(channel_username, text)

        return True
    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")
        return False

@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_", "reject_")))
def handle_callback(call):
    action, row_num, post_id = call.data.split("_")
    row_num = int(row_num)
    print(f"🔁 Callback received: {call.data}")

    if action == "approve":
        sheet.update_cell(row_num, get_col_index("status"), "approved")
        row_data = sheet.row_values(row_num)
        headers = sheet.row_values(1)
        row_dict = dict(zip(headers, row_data))

        success = publish_post(row_dict)
        if success:
            print(f"✅ Approved post {post_id} -> sending to channel {row_dict['channel_username']}")
        else:
            print(f"⚠️ Failed to publish post {post_id}")
    elif action == "reject":
        sheet.update_cell(row_num, get_col_index("status"), "rejected")
        print(f"❌ Rejected post {post_id}")

# === BACKGROUND POLLER ===

def check_pending_loop():
    while True:
        row_num, row_data = get_pending_post()
        if row_data:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
        time.sleep(10)

# === START BOT ===

print("🤖 Campaign Publisher Bot is running...")

threading.Thread(target=check_pending_loop, daemon=True).start()

bot.remove_webhook()
bot.infinity_polling()
