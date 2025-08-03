
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Load environment variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SHEET_ID = os.environ.get("SHEET_ID")
CREDENTIALS_JSON = os.environ.get("GOOGLE_CREDENTIALS_JSON")

bot = telebot.TeleBot(BOT_TOKEN)

# Setup Google Sheets
import json
creds_dict = json.loads(CREDENTIALS_JSON)
scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).worksheet("campaign_posts")

# Get the first pending post
def get_pending_post():
    records = sheet.get_all_records()
    for i, row in enumerate(records, start=2):
        if row['status'].strip().lower() == 'pending':
            return i, row
    return None, None

# Send post for approval
def send_for_approval(row_num, row_data):
    user_id = int(row_data['approver_user_id'])
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

    if media_type == 'photo':
        bot.send_photo(user_id, file_id, caption=text, reply_markup=markup)
    elif media_type == 'video':
        bot.send_video(user_id, file_id, caption=text, reply_markup=markup)
    else:
        bot.send_message(user_id, text, reply_markup=markup)

# Callback handler
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
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

        if action == "approve":
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(cta_text, url=cta_url))
            if media_type == 'photo':
                bot.send_photo(channel_id, media_file_id, caption=post_text, reply_markup=markup)
            elif media_type == 'video':
                bot.send_video(channel_id, media_file_id, caption=post_text, reply_markup=markup)
            else:
                bot.send_message(channel_id, post_text, reply_markup=markup)
            sheet.update_cell(row_num, 12, "posted")
            bot.answer_callback_query(call.id, "✅ Post published")
        else:
            sheet.update_cell(row_num, 12, "rejected")
            bot.answer_callback_query(call.id, "❌ Post rejected")

# Command to start processing
@bot.message_handler(commands=['process'])
def process_pending(message):
    row_num, row_data = get_pending_post()
    if row_data:
        send_for_approval(row_num, row_data)
        bot.reply_to(message, "📤 Sent for approval")
    else:
        bot.reply_to(message, "✅ No pending posts.")

print("🤖 Campaign Publisher Bot is running...")
bot.remove_webhook()
bot.infinity_polling()
