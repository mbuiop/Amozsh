import telebot
from telebot import types
import sqlite3
import os
import sys
import json
from datetime import datetime

if len(sys.argv) < 2:
    print("❌ خطا: آیدی ربات داده نشده")
    sys.exit(1)

BOT_ID = sys.argv[1]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_FOLDER = os.path.join(BASE_DIR, "bots", BOT_ID)
TOKEN_FILE = os.path.join(BOT_FOLDER, "token.txt")
CODE_FILE = os.path.join(BOT_FOLDER, "bot.py")
DB_FILE = os.path.join(BOT_FOLDER, "user_data.db")

# خواندن توکن
try:
    with open(TOKEN_FILE, "r") as f:
        TOKEN = f.read().strip()
except:
    print(f"❌ خطا: توکن برای ربات {BOT_ID} پیدا نشد")
    sys.exit(1)

# راه‌اندازی ربات
bot = telebot.TeleBot(TOKEN)

# دیتابیس
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
conn.execute("PRAGMA journal_mode = WAL")
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_seen TEXT,
    last_seen TEXT,
    messages_count INTEGER DEFAULT 0
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    date TEXT
)
''')

conn.commit()

# ==================== دریافت دکمه‌ها از دیتابیس اصلی ====================
def get_buttons():
    try:
        master_conn = sqlite3.connect(os.path.join(BASE_DIR, 'master.db'))
        master_c = master_conn.cursor()
        master_c.execute('''
            SELECT button_name, button_type, button_data 
            FROM bot_buttons WHERE bot_id = ?
            ORDER BY row_num, col_num
        ''', (BOT_ID,))
        buttons = master_c.fetchall()
        master_conn.close()
        return buttons
    except:
        return []

def create_keyboard():
    buttons = get_buttons()
    if not buttons:
        return None
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    row = []
    
    for name, btn_type, data in buttons:
        row.append(types.KeyboardButton(name))
        if len(row) == 2:
            markup.add(*row)
            row = []
    
    if row:
        markup.add(*row)
    
    return markup

# ==================== شروع ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    now = datetime.now().isoformat()
    
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_seen, last_seen)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, now, now))
    
    c.execute('''
        UPDATE users SET last_seen = ?, messages_count = messages_count + 1
        WHERE user_id = ?
    ''', (now, user_id))
    conn.commit()
    
    # ذخیره پیام
    c.execute('''
        INSERT INTO messages (user_id, message, date)
        VALUES (?, ?, ?)
    ''', (user_id, '/start', now))
    conn.commit()
    
    # دریافت متن خوش‌آمدگویی
    welcome_text = "👋 سلام! به ربات من خوش آمدید."
    
    try:
        master_conn = sqlite3.connect(os.path.join(BASE_DIR, 'master.db'))
        master_c = master_conn.cursor()
        master_c.execute('SELECT welcome_text FROM user_bots WHERE id = ?', (BOT_ID,))
        result = master_c.fetchone()
        if result and result[0]:
            welcome_text = result[0]
        master_conn.close()
    except:
        pass
    
    markup = create_keyboard()
    
    if markup:
        bot.reply_to(message, welcome_text, reply_markup=markup)
    else:
        bot.reply_to(message, welcome_text)

# ==================== هندلر دکمه‌ها ====================
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text
    now = datetime.now().isoformat()
    
    # ذخیره پیام
    c.execute('''
        INSERT INTO messages (user_id, message, date)
        VALUES (?, ?, ?)
    ''', (user_id, text[:500], now))
    conn.commit()
    
    # جستجوی دکمه
    buttons = get_buttons()
    
    for name, btn_type, data in buttons:
        if name == text:
            if btn_type == 'text':
                bot.reply_to(message, data)
            
            elif btn_type == 'link':
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("🔗 باز کردن لینک", url=data))
                bot.reply_to(message, "لینک:", reply_markup=markup)
            
            elif btn_type == 'phone':
                markup = types.InlineKeyboardMarkup()
                markup.add(types.InlineKeyboardButton("📞 تماس", url=f"tel:{data}"))
                bot.reply_to(message, "شماره تلفن:", reply_markup=markup)
            
            elif btn_type == 'code':
                try:
                    exec(data)
                except Exception as e:
                    bot.reply_to(message, f"❌ خطا: {str(e)}")
            
            else:
                bot.reply_to(message, data)
            
            return
    
    # اگر دکمه نبود
    bot.reply_to(message, f"شما گفتید: {text}")

# ==================== آمار ====================
@bot.message_handler(commands=['stats'])
def stats(message):
    user_id = message.from_user.id
    
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM messages')
    total_messages = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM users WHERE last_seen > date("now", "-1 day")')
    active_today = c.fetchone()[0]
    
    bot.send_message(
        message.chat.id,
        f"📊 **آمار ربات**\n\n"
        f"👥 کل کاربران: {total_users}\n"
        f"📝 پیام‌ها: {total_messages}\n"
        f"📅 فعال امروز: {active_today}",
        parse_mode="Markdown"
    )

# ==================== اجرا ====================
if __name__ == "__main__":
    print(f"✅ ربات {BOT_ID} با موفقیت اجرا شد")
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ خطا در ربات {BOT_ID}: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
