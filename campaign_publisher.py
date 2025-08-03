import os
import json
import gspread
import telebot
from time import sleep
from threading import Thread
from oauth2client.service_account import ServiceAccountCredentials
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === Load environment variables ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# === Setup Google Sheets ===
creds_dict = json.loads(CREDENTIALS_JSON)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).worksheet("campaign_posts")

# === Get the first pending post ===
def get_pending_post():
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):  # start=2 because row 1 is headers
        if str(row['status']).strip().lower() == 'pending':
            return i, row
    return None, None

# === Send post for approval ===
def send_for_approval(row_num, row_data):
    try:
        user_id = int(row_data['approver_user_id'])
        text = row_data['text']
        media_type = row_data['media_type']
        file_id = row_data['media_file_id']
        cta_text = row_data['cta_text']
        cta_url = row_data['cta_url']
        post_id = row_data['post_id']

        print(f"📨 Sending post {post_id} to approver {user_id}")

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{row_num}_{post_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{row_num}_{post_id}")
        )

        if media_type == 'photo':
            bot.send_photo(user_id, file_id, caption=text, reply_markup=markup)
        elif media_type == 'video':
            bot.send_video(user_id, file_id, caption=text, reply_markup=markup)
        else:
            bot.send_message(user_id, text, reply_markup=markup)
    except Exception as e:
        print(f"⚠️ Failed to send for approval: {e}")

# === Handle Approve / Reject ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
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
            if not channel_id.startswith("@"):
                channel_id = "@" + channel_id

            print(f"🔁 Callback received: {data}")

            if action == "approve":
                try:
                    markup = InlineKeyboardMarkup()
                    markup.add(InlineKeyboardButton(cta_text, url=cta_url))
                    if media_type == 'photo':
                        bot.send_photo(channel_id, media_file_id, caption=post_text, reply_markup=markup)
                    elif media_type == 'video':
                        bot.send_video(channel_id, media_file_id, caption=post_text, reply_markup=markup)
                    else:
                        bot.send_message(channel_id, post_text, reply_markup=markup)
                    sheet.update_cell(row_num, 12, "posted")
                    print(f"✅ Approved post {post_id} -> sending to channel {channel_id}")
                    bot.answer_callback_query(call.id, "✅ Post published")
                except Exception as e:
                    print(f"⚠️ Failed to publish post: {e}")
                    bot.answer_callback_query(call.id, "⚠️ Failed to publish post")
            else:
                sheet.update_cell(row_num, 12, "rejected")
                print(f"❌ Rejected post {post_id}")
                bot.answer_callback_query(call.id, "❌ Post rejected")
    except Exception as e:
        print(f"⚠️ Callback error: {e}")

# === Command: /process (manual trigger) ===
@bot.message_handler(commands=['process'])
def process_pending(message):
    row_num, row_data = get_pending_post()
    if row_data:
        send_for_approval(row_num, row_data)
        bot.reply_to(message, "📤 Sent for approval")
    else:
        bot.reply_to(message, "✅ No pending posts.")

# === Handle receiving a photo or video (for file_id) ===
@bot.message_handler(content_types=['photo', 'video'])
def handle_media(message):
    if message.photo:
        file_id = message.photo[-1].file_id
        bot.reply_to(message, f"📸 Photo received.\nFile ID:\n`{file_id}`", parse_mode="Markdown")
    elif message.video:
        file_id = message.video.file_id
        bot.reply_to(message, f"🎥 Video received.\nFile ID:\n`{file_id}`", parse_mode="Markdown")

# === Background checker ===
def check_pending_loop():
    while True:
        row_num, row_data = get_pending_post()
        if row_data:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
        sleep(10)

# === Start bot ===
print("🤖 Campaign Publisher Bot is running...")
bot.remove_webhook()
Thread(target=check_pending_loop, daemon=True).start()
bot.infinity_polling()
