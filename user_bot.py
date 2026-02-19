import telebot
from telebot import types
import sqlite3
import os
import sys
from datetime import datetime

# دریافت آیدی کاربر از خط فرمان
if len(sys.argv) > 1:
    USER_ID = sys.argv[1]
else:
    print("❌ خطا: آیدی کاربر داده نشده")
    sys.exit(1)

# مسیرها
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USER_FOLDER = os.path.join(BASE_DIR, "users", USER_ID)
TOKEN_FILE = os.path.join(USER_FOLDER, "token.txt")

# خواندن توکن
try:
    with open(TOKEN_FILE, "r") as f:
        TOKEN = f.read().strip()
except:
    print(f"❌ خطا: توکن برای کاربر {USER_ID} پیدا نشد")
    sys.exit(1)

# راه‌اندازی ربات
bot = telebot.TeleBot(TOKEN)

# دیتابیس مخصوص این ربات
DB_FILE = os.path.join(USER_FOLDER, "user_data.db")
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, first_seen TEXT, last_seen TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS products
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              price INTEGER,
              created_date TEXT)''')
conn.commit()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    now = datetime.now().isoformat()
    
    c.execute('''INSERT OR IGNORE INTO users (user_id, first_seen, last_seen) 
                 VALUES (?, ?, ?)''', (user_id, now, now))
    c.execute('''UPDATE users SET last_seen = ? WHERE user_id = ?''', (now, user_id))
    conn.commit()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('🛍 محصولات')
    btn2 = types.KeyboardButton('📞 پشتیبانی')
    btn3 = types.KeyboardButton('ℹ️ درباره ما')
    btn4 = types.KeyboardButton('📊 آمار')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.reply_to(
        message,
        f"👋 سلام! به ربات من خوش اومدی.",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == '🛍 محصولات')
def products(message):
    c.execute('''SELECT name, price FROM products''')
    items = c.fetchall()
    
    if not items:
        bot.send_message(message.chat.id, "📦 محصولی وجود ندارد.")
        return
    
    text = "🛍 **محصولات:**\n\n"
    for name, price in items:
        text += f"• {name} - {price:,} تومان\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '📊 آمار')
def stats(message):
    c.execute('''SELECT COUNT(*) FROM users''')
    users = c.fetchone()[0]
    
    c.execute('''SELECT COUNT(*) FROM products''')
    products = c.fetchone()[0]
    
    bot.send_message(
        message.chat.id,
        f"📊 **آمار:**\n\n"
        f"👥 کاربران: {users}\n"
        f"📦 محصولات: {products}"
    )

@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(message.chat.id, "📞 @support")

@bot.message_handler(func=lambda m: m.text == 'ℹ️ درباره ما')
def about(message):
    bot.send_message(message.chat.id, "ℹ️ این ربات توسط ربات ساز حرفه‌ای ساخته شده.")

if __name__ == "__main__":
    print(f"✅ ربات کاربر {USER_ID} فعال شد...")
    bot.infinity_polling()
