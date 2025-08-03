import os
import gspread
import telebot
import json
import threading
import time
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === CONFIGURATION ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# === GOOGLE SHEETS SETUP ===
creds_dict = json.loads(CREDENTIALS_JSON)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).worksheet("campaign_posts")

# === GET FIRST PENDING POST ===
def get_pending_post():
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):
        if row['status'].strip().lower() == 'pending':
            sheet.update_cell(i, 12, 'processing')  # prevent duplicate sends
            return i, row
    return None, None

# === SEND POST FOR APPROVAL ===
def send_for_approval(row_num, row_data):
    try:
        user_id = int(row_data['approver_user_id'])  # must be numeric
    except Exception as e:
        print(f"⚠️ 'approver_user_id' must be a Telegram numeric user ID. Error: {e}")
        return

    text = row_data['text']
    media_type = row_data['media_type']
    file_id = row_data['media_file_id']
    cta_text = row_data['cta_text']
    cta_url = row_data['cta_url']
    post_id = row_data['post_id']

    markup = InlineKeyboardMarkup()
    markup.add(
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{row_num}_{post_id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{row_num}_{post_id}")
    )

    print(f"📨 Sending post {post_id} to approver {user_id}")
    if media_type == 'photo':
        bot.send_photo(user_id, file_id, caption=text, reply_markup=markup)
    elif media_type == 'video':
        bot.send_video(user_id, file_id, caption=text, reply_markup=markup)
    else:
        bot.send_message(user_id, text, reply_markup=markup)

# === CALLBACK HANDLER ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    print(f"🔁 Callback received: {call.data}")
    data = call.data
    if data.startswith("approve_") or data.startswith("reject_"):
        action, row_num, post_id = data.split("_")
        row_num = int(row_num)
        row = sheet.row_values(row_num)

        post_text = row[6]
        media_type = row[7]
        media_file_id = row[8]
        cta_text = row[9]
        cta_url = row[10]
        channel_id = row[2]

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(cta_text, url=cta_url))

        try:
            if action == "approve":
                print(f"✅ Approved post {post_id} -> sending to channel {channel_id}")
                if media_type == 'photo':
                    bot.send_photo(channel_id, media_file_id, caption=post_text, reply_markup=markup)
                elif media_type == 'video':
                    bot.send_video(channel_id, media_file_id, caption=post_text, reply_markup=markup)
                else:
                    bot.send_message(channel_id, post_text, reply_markup=markup)
                sheet.update_cell(row_num, 12, "posted")
                bot.answer_callback_query(call.id, "✅ Post published")
            else:
                print(f"❌ Rejected post {post_id}")
                sheet.update_cell(row_num, 12, "rejected")
                bot.answer_callback_query(call.id, "❌ Post rejected")
        except Exception as e:
            print(f"⚠️ Failed to publish post: {e}")
            bot.answer_callback_query(call.id, "⚠️ Error publishing post")

# === AUTO CHECK LOOP ===
def check_pending_loop():
    while True:
        row_num, row_data = get_pending_post()
        if row_data:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
        time.sleep(10)

# === BOT START ===
print("🤖 Campaign Publisher Bot is running...")
threading.Thread(target=check_pending_loop, daemon=True).start()
bot.remove_webhook()
bot.infinity_polling()
