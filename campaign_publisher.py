import os
import time
import threading
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from telebot import TeleBot, types

# קריאת משתני סביבה ישירות מ-Railway
BOT_TOKEN = os.getenv("BOT_TOKEN")
SHEET_ID = os.getenv("SHEET_ID")
APPROVER_ID = int(os.getenv("APPROVER_ID"))
CREDENTIALS_PATH = "credentials.json"

bot = TeleBot(BOT_TOKEN)

# התחברות לגוגל שיט
scope = ['https://spreadsheets.google.com/feeds',
         'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_PATH, scope)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_ID).sheet1

def get_pending_post():
    rows = sheet.get_all_records()
    for idx, row in enumerate(rows, start=2):
        if row.get("status", "").lower() == "pending":
            return idx, row
    return None, None

def update_status(row_num, new_status):
    sheet.update_cell(row_num, 7, new_status)  # עמודה G = status

def extract_url_from_text(text):
    words = text.strip().split()
    for word in reversed(words):
        if word.startswith("http://") or word.startswith("https://"):
            return word, " ".join(words[:-1])
    return "", text

def send_for_approval(row_num, row_data):
    channel = row_data["channel"]
    text = row_data["text"]
    media_id = row_data.get("media_id", "")
    post_id = row_data["post_id"]

    url, caption = extract_url_from_text(text)

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✅ אישור", callback_data=f"approve_{row_num}_{post_id}"))
    markup.add(types.InlineKeyboardButton("❌ דחייה", callback_data=f"reject_{row_num}_{post_id}"))

    try:
        if media_id:
            bot.send_photo(APPROVER_ID, media_id, caption=caption + f"\n\n{url}", reply_markup=markup)
        else:
            bot.send_message(APPROVER_ID, caption + f"\n\n{url}", reply_markup=markup)
    except Exception as e:
        print(f"⚠️ Failed to send for approval: {e}")

def publish_post(channel, media_id, text):
    url, caption = extract_url_from_text(text)
    try:
        if media_id:
            bot.send_photo(f"@{channel}", media_id, caption=caption + f"\n\n{url}")
        else:
            bot.send_message(f"@{channel}", caption + f"\n\n{url}")
        return True
    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")
        return False

@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_"))
def handle_approve(call):
    try:
        _, row_num, post_id = call.data.split("_")
        row_num = int(row_num)
        row_data = sheet.row_values(row_num)
        headers = sheet.row_values(1)
        data = dict(zip(headers, row_data))

        print(f"✅ Approved post {post_id} -> sending to channel {data['channel']}")

        success = publish_post(data["channel"], data.get("media_id", ""), data["text"])
        if success:
            update_status(row_num, "approved")
            bot.send_message(APPROVER_ID, f"✅ פוסט {post_id} פורסם בהצלחה.")
        else:
            bot.send_message(APPROVER_ID, f"❌ לא הצלחנו לפרסם את הפוסט {post_id}.")
    except Exception as e:
        print(f"⚠️ Error in approval callback: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_"))
def handle_reject(call):
    try:
        _, row_num, post_id = call.data.split("_")
        row_num = int(row_num)
        update_status(row_num, "rejected")
        bot.send_message(APPROVER_ID, f"🚫 פוסט {post_id} נדחה.")
    except Exception as e:
        print(f"⚠️ Error in rejection callback: {e}")

def check_loop():
    while True:
        row_num, row_data = get_pending_post()
        if row_data:
            print(f"📤 Found pending post: {row_data['post_id']}")
            send_for_approval(row_num, row_data)
            time.sleep(5)  # כדי למנוע שליחה כפולה
        else:
            time.sleep(10)

# Start
print("🤖 Campaign Publisher Bot is running...")
threading.Thread(target=check_loop, daemon=True).start()
bot.remove_webhook()
bot.infinity_polling()
