import os
import time
import threading
import telebot
import gspread
from google.oauth2.service_account import Credentials

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON")

# Telegram bot setup
bot = telebot.TeleBot(BOT_TOKEN)

# Google Sheets setup
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
creds = Credentials.from_service_account_info(eval(GOOGLE_CREDENTIALS_JSON), scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).sheet1

# Get all rows and headers
def get_sheet_data():
    records = sheet.get_all_records()
    return records

def update_status(row_num, new_status):
    sheet.update_cell(row_num + 2, 12, new_status)  # column L (12) = status

# Send post to approver
def send_for_approval(row_num, row_data):
    approver_id = row_data.get("approver_id")
    if not approver_id:
        print("⚠️ Missing 'approver_id'")
        return

    try:
        approver_id = int(approver_id)
    except ValueError:
        print("⚠️ Invalid 'approver_id'")
        return

    post_id = row_data.get("post_id")
    text = row_data.get("text", "")
    url = row_data.get("cta_url", "")
    if url:
        text += f"\n\n{url}"
    media_type = row_data.get("media_type", "").lower()
    media_file_id = row_data.get("media_file_id", "")

    markup = telebot.types.InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        telebot.types.InlineKeyboardButton("✅ אשר", callback_data=f"approve_{row_num}_{post_id}"),
        telebot.types.InlineKeyboardButton("❌ דחה", callback_data=f"reject_{row_num}_{post_id}")
    )

    try:
        if media_type == "photo" and media_file_id:
            bot.send_photo(approver_id, media_file_id, caption=text, reply_markup=markup)
        else:
            bot.send_message(approver_id, text, reply_markup=markup)
        update_status(row_num, "waiting_approval")
        print(f"📨 Sent post {post_id} to approver {approver_id}")
    except Exception as e:
        print(f"⚠️ Error sending for approval: {e}")

# Publish to Telegram channel
def publish_post(row_num, row_data):
    channel_id = row_data.get("channel_id")
    text = row_data.get("text", "")
    url = row_data.get("cta_url", "")
    if url:
        text += f"\n\n{url}"
    media_type = row_data.get("media_type", "").lower()
    media_file_id = row_data.get("media_file_id", "")

    try:
        if media_type == "photo" and media_file_id:
            bot.send_photo(channel_id, media_file_id, caption=text)
        else:
            bot.send_message(channel_id, text)
        update_status(row_num, "published")
        print(f"✅ Approved post {row_data.get('post_id')} -> sent to channel {channel_id}")
    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")

# Handle button callbacks
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    try:
        action, row_num, post_id = call.data.split("_")
        row_num = int(row_num)
        data = get_sheet_data()
        if row_num >= len(data):
            print(f"⚠️ Row {row_num} out of range")
            return

        row_data = data[row_num]

        if action == "approve":
            publish_post(row_num, row_data)
        elif action == "reject":
            update_status(row_num, "rejected")
            print(f"❌ Rejected post {post_id}")
    except Exception as e:
        print(f"⚠️ Callback error: {e}")

# Loop to check for new posts
def check_pending_loop():
    while True:
        try:
            data = get_sheet_data()
            for i, row in enumerate(data):
                if row.get("status", "").lower() == "pending":
                    print(f"📤 Found pending post: {row.get('post_id')}")
                    send_for_approval(i, row)
        except Exception as e:
            print(f"⚠️ Error checking sheet: {e}")
        time.sleep(10)

# Start thread and bot
threading.Thread(target=check_pending_loop, daemon=True).start()
print("🤖 Campaign Publisher Bot is running...")
bot.infinity_polling()
