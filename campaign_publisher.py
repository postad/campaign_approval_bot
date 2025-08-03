import os
import time
import threading
import telebot
import gspread
from google.oauth2.service_account import Credentials

# Telegram Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
bot = telebot.TeleBot(BOT_TOKEN)

# Google Sheets setup
SHEET_ID = os.getenv("SHEET_ID")
CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")
credentials = Credentials.from_service_account_info(eval(CREDENTIALS_JSON), scopes=["https://www.googleapis.com/auth/spreadsheets"])
gc = gspread.authorize(credentials)
sh = gc.open_by_key(SHEET_ID)
worksheet = sh.worksheet("campaign_posts")

def get_pending_post():
    records = worksheet.get_all_records()
    for idx, row in enumerate(records):
        if row.get("status", "").lower() == "pending":
            return idx + 2, row  # +2 to match Google Sheets row (including header)
    return None, None

def send_for_approval(row_num, row_data):
    try:
        approver_id = int(row_data["approver_id"])
        text = row_data["text"]
        url = row_data.get("url", "")
        full_text = f"{text.strip()}\n\n{url.strip()}" if url else text.strip()

        markup = telebot.types.InlineKeyboardMarkup()
        approve_button = telebot.types.InlineKeyboardButton("✅ Approve", callback_data=f"approve_{row_num}_{row_data['post_id']}")
        markup.add(approve_button)

        if row_data.get("media_type", "").lower() == "image" and row_data.get("media_id"):
            bot.send_photo(approver_id, row_data["media_id"], caption=full_text, parse_mode="HTML", reply_markup=markup)
        else:
            bot.send_message(approver_id, full_text, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        print(f"⚠️ Error sending for approval: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def handle_approval(call):
    try:
        print(f"🔁 Callback received: {call.data}")
        _, row_num, post_id = call.data.split("_")
        row_num = int(row_num)

        row_data = worksheet.row_values(row_num)
        headers = worksheet.row_values(1)
        row_dict = dict(zip(headers, row_data))

        channel_username = row_dict["channel_username"]
        text = row_dict["text"]
        url = row_dict.get("url", "")
        full_text = f"{text.strip()}\n\n{url.strip()}" if url else text.strip()

        if row_dict.get("media_type", "").lower() == "image" and row_dict.get("media_id"):
            bot.send_photo(f"@{channel_username}", row_dict["media_id"], caption=full_text, parse_mode="HTML")
        else:
            bot.send_message(f"@{channel_username}", full_text, parse_mode="HTML")

        worksheet.update_cell(row_num, headers.index("status") + 1, "published")
        bot.answer_callback_query(call.id, "✅ Post published.")
        print(f"✅ Approved post {post_id} -> sent to channel {channel_username}")
    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")
        bot.answer_callback_query(call.id, f"Error: {e}")

def check_pending_loop():
    while True:
        row_num, row_data = get_pending_post()
        if row_data:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
        time.sleep(10)

print("🤖 Campaign Publisher Bot is running...")

threading.Thread(target=check_pending_loop, daemon=True).start()

bot.remove_webhook()
bot.infinity_polling()
