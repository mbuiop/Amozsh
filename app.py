import telebot
from telebot import types
import sqlite3
import os
import sys
import json
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
DATA_FILE = os.path.join(USER_FOLDER, "data.json")

# خواندن توکن
try:
    with open(TOKEN_FILE, "r") as f:
        TOKEN = f.read().strip()
except:
    print("❌ خطا: توکن پیدا نشد")
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
        f"👋 سلام! به ربات من خوش اومدی.\n"
        f"تعداد کاربران: {get_users_count()}",
        reply_markup=markup
    )

def get_users_count():
    c.execute('''SELECT COUNT(*) FROM users''')
    return c.fetchone()[0]

@bot.message_handler(func=lambda m: m.text == '🛍 محصولات')
def products(message):
    c.execute('''SELECT name, price FROM products''')
    items = c.fetchall()
    
    if not items:
        bot.send_message(message.chat.id, "📦 هنوز محصولی ثبت نشده.")
        return
    
    text = "🛍 **محصولات ما:**\n\n"
    for name, price in items:
        text += f"• {name} - {price:,} تومان\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '📊 آمار')
def stats(message):
    users = get_users_count()
    bot.send_message(
        message.chat.id,
        f"📊 **آمار ربات:**\n\n"
        f"👥 تعداد کاربران: {users}",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(
        message.chat.id,
        "📞 برای پشتیبانی به @support پیام بدید."
    )

@bot.message_handler(func=lambda m: m.text == 'ℹ️ درباره ما')
def about(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ این ربات توسط ربات ساز حرفه‌ای ساخته شده."
    )

# ==================== بخش مدیریت (فقط برای مالک) ====================
@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if str(message.from_user.id) != USER_ID:
        bot.reply_to(message, "⛔ شما دسترسی ندارید!")
        return
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('➕ افزودن محصول')
    btn2 = types.KeyboardButton('📋 لیست محصولات')
    btn3 = types.KeyboardButton('🗑 حذف محصول')
    btn4 = types.KeyboardButton('🔙 بازگشت')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(
        message.chat.id,
        "👑 **پنل مدیریت**\n\n"
        "یکی از گزینه‌ها رو انتخاب کن:",
        reply_markup=markup
    )

@bot.message_handler(func=lambda m: m.text == '➕ افزودن محصول')
def add_product_name(message):
    if str(message.from_user.id) != USER_ID:
        return
    msg = bot.send_message(message.chat.id, "📦 اسم محصول رو بنویس:")
    bot.register_next_step_handler(msg, add_product_price)

def add_product_price(message):
    product_name = message.text.strip()
    msg = bot.send_message(message.chat.id, f"💰 قیمت {product_name} رو به تومان بنویس:")
    bot.register_next_step_handler(msg, save_product, product_name)

def save_product(message, product_name):
    try:
        price = int(message.text.strip())
        c.execute('''INSERT INTO products (name, price, created_date)
                     VALUES (?, ?, ?)''',
                  (product_name, price, datetime.now().isoformat()))
        conn.commit()
        bot.send_message(message.chat.id, f"✅ محصول '{product_name}' با قیمت {price:,} تومان اضافه شد!")
    except:
        bot.send_message(message.chat.id, "❌ لطفاً عدد معتبر وارد کن.")

@bot.message_handler(func=lambda m: m.text == '📋 لیست محصولات')
def admin_products(message):
    if str(message.from_user.id) != USER_ID:
        return
    c.execute('''SELECT name, price FROM products''')
    items = c.fetchall()
    
    if not items:
        bot.send_message(message.chat.id, "📦 محصولی وجود ندارد.")
        return
    
    text = "📋 **لیست محصولات:**\n\n"
    for name, price in items:
        text += f"• {name} - {price:,} تومان\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '🗑 حذف محصول')
def delete_product_list(message):
    if str(message.from_user.id) != USER_ID:
        return
    
    c.execute('''SELECT id, name, price FROM products''')
    items = c.fetchall()
    
    if not items:
        bot.send_message(message.chat.id, "📦 محصولی برای حذف وجود ندارد.")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for pid, name, price in items:
        btn = types.InlineKeyboardButton(
            f"❌ {name} - {price:,} تومان",
            callback_data=f"del_{pid}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "🗑 محصول مورد نظر برای حذف رو انتخاب کن:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('del_'))
def delete_product(call):
    if str(call.from_user.id) != USER_ID:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    pid = call.data.replace('del_', '')
    c.execute('''DELETE FROM products WHERE id = ?''', (pid,))
    conn.commit()
    
    bot.answer_callback_query(call.id, "✅ محصول حذف شد!")
    bot.edit_message_text(
        "✅ محصول با موفقیت حذف شد.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda m: m.text == '🔙 بازگشت')
def back_to_main(message):
    if str(message.from_user.id) != USER_ID:
        return
    start(message)

if __name__ == "__main__":
    print(f"✅ ربات کاربر {USER_ID} فعال شد...")
    bot.infinity_polling()
