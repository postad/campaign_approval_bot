
import telebot
import gspread
import threading
import time
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# === CONFIGURATION ===
BOT_TOKEN = "your-bot-token-here"
SHEET_ID = "your-google-sheet-id"
APPROVAL_RANGE = "campaign_posts!A2:Z"  # Adjust if needed

bot = telebot.TeleBot(BOT_TOKEN)

# === GOOGLE SHEET SETUP ===
gc = gspread.service_account(filename="credentials.json")
sheet = gc.open_by_key(SHEET_ID).worksheet("campaign_posts")

# === HELPER FUNCTIONS ===
def get_pending_post():
    records = sheet.get_all_records()
    for idx, row in enumerate(records, start=2):
        if str(row.get('status', '')).lower() == "pending":
            return idx, row
    return None, None

def update_status(row_num, status):
    sheet.update_cell(row_num, 7, status)  # Assuming column G is 'status'

def send_for_approval(row_num, row_data):
    try:
        user_id = int(row_data['approver_user_id'])
        post_id = row_data['post_id']
        text = row_data['text']
        file_id = row_data.get('media_file_id', '').strip()
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{row_num}_{post_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{row_num}_{post_id}")
        )
        if file_id:
            bot.send_photo(user_id, file_id, caption=text, reply_markup=markup)
        else:
            bot.send_message(user_id, text, reply_markup=markup)
        print(f"📨 Sending post {post_id} to approver {user_id}")
    except Exception as e:
        print(f"⚠️ Failed to send for approval: {e}")

def publish_post(row_data):
    try:
        channel_username = row_data['channel_username']
        text = row_data['text']
        file_id = row_data.get('media_file_id', '').strip()
        if file_id:
            bot.send_photo(channel_username, file_id, caption=text)
        else:
            bot.send_message(channel_username, text)
        return True
    except Exception as e:
        print(f"⚠️ Failed to publish post: {e}")
        return False

# === TELEGRAM HANDLERS ===
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        data = call.data
        print(f"🔁 Callback received: {data}")
        action, row_num, post_id = data.split("_")
        row_num = int(row_num)
        row_data = sheet.row_values(row_num)
        headers = sheet.row_values(1)
        row_dict = dict(zip(headers, row_data))

        if action == "approve":
            update_status(row_num, "approved")
            success = publish_post(row_dict)
            if success:
                bot.send_message(call.from_user.id, f"✅ Approved post {post_id} -> sending to channel {row_dict['channel_username']}")
        elif action == "reject":
            update_status(row_num, "rejected")
            bot.send_message(call.from_user.id, f"❌ Rejected post {post_id}")
    except Exception as e:
        print(f"⚠️ Error handling callback: {e}")

@bot.message_handler(content_types=['photo'])
def get_file_id(message):
    file_id = message.photo[-1].file_id
    bot.reply_to(message, f"✅ file_id:\n{file_id}")
    print(f"📷 Received photo. file_id = {file_id}")

# === POLLING LOOP ===
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
