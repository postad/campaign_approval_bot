import os
import time
import threading
import telebot
from telebot import types
import gspread

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
CREDENTIALS_PATH = "credentials.json"

# Connect to Telegram Bot
bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')

# Connect to Google Sheet
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).sheet1

# Helper: Get pending post
def get_pending_post():
    records = sheet.get_all_records()
    for idx, row in enumerate(records, start=2):  # Start from row 2
        if row.get("status", "").strip().lower() == "pending":
            return idx, row
    return None, None

# Helper: Send post for approval
def send_for_approval(row_num, row_data):
    try:
        user_id = int(row_data['approver_user_id'])
        channel = row_data['channel_username']
        text = row_data['text']
        media_id = row_data['media_file_id']
        post_id = row_data['post_id']
        cta_url = row_data['cta_url']

        # Append URL to end of message if present
        if cta_url:
            text += f"\n\n{cta_url}"

        approve_cb = f"approve_{row_num}_{post_id}"
        reject_cb = f"reject_{row_num}_{post_id}"

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ אישור", callback_data=approve_cb),
            types.InlineKeyboardButton("❌ דחיה", callback_data=reject_cb)
        )

        if media_id:
            bot.send_photo(user_id, media_id, caption=text, reply_markup=markup)
        else:
            bot.send_message(user_id, text, reply_markup=markup)

        print(f"📨 Sending post {post_id} to approver {user_id}")
        sheet.update_cell(row_num, 12, "processing")

    except Exception as e:
        print(f"⚠️ Error sending for approval: {e}")

# Helper: Publish to Telegram channel
def publish_post(row_num, row_data):
    try:
        channel = row_data['channel_username']
        text = row_data['text']
        media_id = row_data['media_file_id']
        cta_url = row_data['cta_url']
        post_id = row_data['post_id']

        if cta_url:
            text += f"\n\n{cta_url}"

        target = f"@{channel}" if not channel.startswith("@") else channel

        if media_id:
            bot.send_photo(target, media_id, caption=text)
        else:
            bot.send_message(target, text)

        sheet.update_cell(row_num, 12, "published")
        print(f"✅ Approved post {post_id} -> sent to channel {target}")

    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")

# Handle button clicks
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    print(f"🔁 Callback received: {data}")
    try:
        action, row_num, post_id = data.split("_")
        row_num = int(row_num)
        row_data = sheet.row_values(row_num)
        headers = sheet.row_values(1)
        data_dict = dict(zip(headers, row_data))

        if action == "approve":
            publish_post(row_num, data_dict)
        elif action == "reject":
            sheet.update_cell(row_num, 12, "rejected")
            bot.send_message(call.from_user.id, f"❌ Rejected post {post_id}")
    except Exception as e:
        print(f"⚠️ Callback error: {e}")

# Background loop to check for new pending posts
def check_pending_loop():
    while True:
        row_num, row_data = get_pending_post()
        if row_data:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
        time.sleep(10)

# Start the bot
print("🤖 Campaign Publisher Bot is running...")
threading.Thread(target=check_pending_loop, daemon=True).start()
bot.remove_webhook()
bot.infinity_polling()
