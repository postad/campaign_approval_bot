import os
import time
import threading
import telebot
import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# --- Google Auth
import json
creds_dict = json.loads(CREDENTIALS_JSON)
creds = Credentials.from_service_account_info(creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).worksheet("campaign_posts")

bot = telebot.TeleBot(BOT_TOKEN)

def get_pending_post():
    data = sheet.get_all_records()
    for i, row in enumerate(data, start=2):
        if row["status"].lower() == "pending":
            return i, row
    return None, None

def update_status(row_num, status):
    sheet.update_cell(row_num, 7, status)

def parse_text_and_url(text):
    parts = text.strip().split()
    if parts and parts[-1].startswith("http"):
        return " ".join(parts[:-1]), parts[-1]
    return text, None

def send_for_approval(row_num, row_data):
    text_body, url = parse_text_and_url(row_data["text"])
    approver_id = int(row_data["approver_id"])
    post_id = row_data["post_id"]

    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ לאשר", callback_data=f"approve_{row_num}_{post_id}"),
        InlineKeyboardButton("❌ לדחות", callback_data=f"reject_{row_num}_{post_id}")
    )

    if row_data["media_type"] == "image":
        try:
            bot.send_photo(
                approver_id,
                row_data["media_id"],
                caption=f"{text_body}\n\n{url if url else ''}".strip(),
                reply_markup=markup
            )
        except Exception as e:
            print(f"⚠️ Failed to send photo: {e}")
    else:
        bot.send_message(approver_id, f"{text_body}\n\n{url if url else ''}".strip(), reply_markup=markup)

    print(f"📨 Sending post {post_id} to approver {approver_id}")

def publish_post(row_data):
    text_body, url = parse_text_and_url(row_data["text"])
    full_text = f"{text_body}\n\n{url if url else ''}".strip()

    try:
        if row_data["media_type"] == "image":
            bot.send_photo(row_data["channel_username"], row_data["media_id"], caption=full_text)
        else:
            bot.send_message(row_data["channel_username"], full_text)

        print(f"✅ Approved post {row_data['post_id']} -> sent to channel {row_data['channel_username']}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")
        return False

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    print(f"🔁 Callback received: {call.data}")
    if call.data.startswith("approve_"):
        _, row_num, post_id = call.data.split("_")
        row_num = int(row_num)
        row_data = sheet.row_values(row_num)
        headers = sheet.row_values(1)
        row_dict = dict(zip(headers, row_data))
        success = publish_post(row_dict)
        if success:
            update_status(row_num, "approved")
    elif call.data.startswith("reject_"):
        _, row_num, post_id = call.data.split("_")
        update_status(int(row_num), "rejected")
        print(f"❌ Rejected post {post_id}")

def check_pending_loop():
    already_sent = set()
    while True:
        row_num, row_data = get_pending_post()
        if row_data and row_data["post_id"] not in already_sent:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
            already_sent.add(row_data["post_id"])
        time.sleep(10)

# --- Start Bot
print("🤖 Campaign Publisher Bot is running...")

threading.Thread(target=check_pending_loop, daemon=True).start()

bot.remove_webhook()
bot.infinity_polling()
