import telebot
from telebot import types
import sqlite3
import os
import sys
import json
import time
import threading
from datetime import datetime

if len(sys.argv) < 3:
    print("❌ خطا: آیدی ربات و پورت داده نشده")
    sys.exit(1)

BOT_ID = sys.argv[1]
PORT = int(sys.argv[2])

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

# خواندن کد (اگر وجود داشت)
CUSTOM_CODE = None
if os.path.exists(CODE_FILE):
    with open(CODE_FILE, "r", encoding='utf-8') as f:
        CUSTOM_CODE = f.read()

# راه‌اندازی ربات
bot = telebot.TeleBot(TOKEN)

# دیتابیس
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              username TEXT,
              first_seen TEXT, 
              last_seen TEXT,
              messages_count INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS products
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              price INTEGER,
              description TEXT,
              photo TEXT,
              created_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS buttons
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              button_name TEXT,
              button_type TEXT,
              button_action TEXT,
              row_number INTEGER,
              col_number INTEGER)''')
conn.commit()

# ==================== توابع کمکی ====================
def get_buttons_markup():
    """ایجاد دکمه‌ها از دیتابیس"""
    c.execute('''SELECT button_name, button_type, button_action FROM buttons ORDER BY row_number, col_number''')
    buttons = c.fetchall()
    
    if not buttons:
        return None
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    row = []
    for name, btn_type, action in buttons:
        row.append(types.KeyboardButton(name))
        if len(row) == 2:
            markup.add(*row)
            row = []
    if row:
        markup.add(*row)
    
    return markup

# ==================== هندلرهای اصلی ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    now = datetime.now().isoformat()
    
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, first_seen, last_seen) 
                 VALUES (?, ?, ?, ?)''', (user_id, username, now, now))
    c.execute('''UPDATE users SET last_seen = ?, messages_count = messages_count + 1 WHERE user_id = ?''',
              (now, user_id))
    conn.commit()
    
    # دریافت متن خوش‌آمدگویی از دیتابیس اصلی
    try:
        master_conn = sqlite3.connect(os.path.join(BASE_DIR, 'master_bot.db'))
        master_c = master_conn.cursor()
        master_c.execute('''SELECT welcome_text FROM user_bots WHERE id = ?''', (BOT_ID,))
        result = master_c.fetchone()
        welcome = result[0] if result else "👋 سلام! به ربات من خوش اومدی."
        master_conn.close()
    except:
        welcome = "👋 سلام! به ربات من خوش اومدی."
    
    markup = get_buttons_markup()
    
    if markup:
        bot.reply_to(message, welcome, reply_markup=markup)
    else:
        bot.reply_to(message, welcome)

# ==================== هندلر دکمه‌ها ====================
@bot.message_handler(func=lambda message: True)
def handle_buttons(message):
    text = message.text
    
    # جستجوی دکمه در دیتابیس
    c.execute('''SELECT button_type, button_action FROM buttons WHERE button_name = ?''', (text,))
    result = c.fetchone()
    
    if result:
        btn_type, action = result
        
        if btn_type == "text":
            bot.reply_to(message, action)
        
        elif btn_type == "link":
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton("🔗 باز کردن لینک", url=action)
            markup.add(btn)
            bot.reply_to(message, "لینک مورد نظر:", reply_markup=markup)
        
        elif btn_type == "code":
            try:
                exec(action)
                bot.reply_to(message, "✅ کد اجرا شد!")
            except Exception as e:
                bot.reply_to(message, f"❌ خطا در اجرا:\n{str(e)}")
        
        else:
            bot.reply_to(message, f"نوع دکمه: {btn_type}\nمقدار: {action}")
    else:
        # اگر کد سفارشی داریم، اجرا کن
        if CUSTOM_CODE:
            try:
                exec(CUSTOM_CODE)
            except:
                pass

# ==================== اجرا ====================
if __name__ == "__main__":
    print(f"✅ ربات {BOT_ID} روی پورت {PORT} اجرا شد")
    bot.infinity_polling()
