import telebot
from telebot import types
import sqlite3
import json
import os
import subprocess
import sys
import time
import shutil
from datetime import datetime, timedelta

# ==================== تنظیمات مسیر ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
os.makedirs(USERS_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

TOKEN = "7956758689:AAH3JZ3kzBybVqPwRZ_pXlyA7Pez0n3BZ0o"
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

# ==================== دیتابیس اصلی ====================
DB_PATH = os.path.join(BASE_DIR, 'bot_designer.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, username TEXT, balance INTEGER DEFAULT 0, 
              plan TEXT DEFAULT 'free', expire_date TEXT, joined_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_bots
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              bot_token TEXT UNIQUE,
              bot_name TEXT,
              bot_username TEXT,
              description TEXT,
              welcome_text TEXT,
              buttons TEXT,
              admins TEXT,
              products TEXT,
              payment_gateway TEXT,
              pid INTEGER,
              status TEXT,
              created_date TEXT,
              last_active TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS templates
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              description TEXT,
              category TEXT,
              price INTEGER,
              file_path TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS temp
             (user_id INTEGER PRIMARY KEY, 
              step TEXT,
              data TEXT)''')
conn.commit()

# ==================== قالب‌های آماده ====================
def init_templates():
    templates = [
        {"name": "ربات فروشگاهی", "category": "shop", "price": 0, "desc": "مناسب برای فروش محصولات"},
        {"name": "ربات پشتیبانی", "category": "support", "price": 0, "desc": "پشتیبانی ۲۴ ساعته"},
        {"name": "ربات اطلاع‌رسانی", "category": "news", "price": 0, "desc": "ارسال اخبار و اطلاعیه"},
        {"name": "ربات رزرو نوبت", "category": "booking", "price": 50000, "desc": "رزرو آنلاین نوبت"},
        {"name": "ربات دانلود", "category": "download", "price": 30000, "desc": "دانلود فایل و محتوا"},
        {"name": "ربات همسان‌یابی", "category": "dating", "price": 100000, "desc": "پیدا کردن همسر"},
    ]
    
    for t in templates:
        c.execute('''INSERT OR IGNORE INTO templates (name, description, category, price) 
                     VALUES (?, ?, ?, ?)''', (t["name"], t["desc"], t["category"], t["price"]))
    conn.commit()

init_templates()

# ==================== توابع کمکی ====================
def get_user_folder(user_id):
    return os.path.join(USERS_DIR, str(user_id))

def save_temp(user_id, step, data=None):
    c.execute('''INSERT OR REPLACE INTO temp (user_id, step, data) VALUES (?, ?, ?)''',
              (user_id, step, json.dumps(data) if data else None))
    conn.commit()

def get_temp(user_id):
    c.execute('''SELECT step, data FROM temp WHERE user_id = ?''', (user_id,))
    row = c.fetchone()
    if row:
        step, data = row
        return step, json.loads(data) if data else {}
    return None, {}

def clear_temp(user_id):
    c.execute('''DELETE FROM temp WHERE user_id = ?''', (user_id,))
    conn.commit()

def run_user_bot(user_id, token):
    """اجرای ربات کاربر"""
    try:
        user_folder = get_user_folder(user_id)
        os.makedirs(user_folder, exist_ok=True)
        
        with open(os.path.join(user_folder, "token.txt"), "w") as f:
            f.write(token)
        
        process = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "user_bot.py"), str(user_id)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return process.pid
    except Exception as e:
        print(f"خطا: {e}")
        return None

# ==================== منوی اصلی ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, joined_date) 
                 VALUES (?, ?, ?)''', (user_id, username, datetime.now().isoformat()))
    conn.commit()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('🤖 ساخت ربات جدید')
    btn2 = types.KeyboardButton('🎨 طراحی ربات')
    btn3 = types.KeyboardButton('📋 ربات‌های من')
    btn4 = types.KeyboardButton('📦 قالب‌های آماده')
    btn5 = types.KeyboardButton('💰 کیف پول')
    btn6 = types.KeyboardButton('📚 راهنما')
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    
    bot.send_message(
        message.chat.id,
        "🎨 **به استودیو طراحی ربات خوش آمدید!**\n\n"
        "اینجا می‌تونی ربات خودتو حرفه‌ای طراحی کنی:\n"
        "✅ انتخاب قالب آماده\n"
        "✅ طراحی دکمه‌ها\n"
        "✅ افزودن محصولات\n"
        "✅ اتصال درگاه پرداخت\n"
        "✅ مدیریت کاربران\n\n"
        "👇 یکی از گزینه‌ها رو انتخاب کن:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==================== طراحی ربات ====================
@bot.message_handler(func=lambda m: m.text == '🎨 طراحی ربات')
def design_bot(message):
    user_id = message.from_user.id
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔘 طراحی دکمه‌ها", callback_data="design_buttons")
    btn2 = types.InlineKeyboardButton("🎨 انتخاب تم", callback_data="design_theme")
    btn3 = types.InlineKeyboardButton("📝 متن خوش‌آمدگویی", callback_data="design_welcome")
    btn4 = types.InlineKeyboardButton("📦 مدیریت محصولات", callback_data="design_products")
    btn5 = types.InlineKeyboardButton("💰 درگاه پرداخت", callback_data="design_payment")
    btn6 = types.InlineKeyboardButton("👑 مدیریت ادمین‌ها", callback_data="design_admins")
    btn7 = types.InlineKeyboardButton("📊 آمار و گزارش", callback_data="design_stats")
    btn8 = types.InlineKeyboardButton("🔙 بازگشت", callback_data="design_back")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8)
    
    # دریافت لیست ربات‌های کاربر
    c.execute('''SELECT id, bot_name FROM user_bots WHERE user_id = ? AND status = 'running' ''', (user_id,))
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "❌ شما ربات فعالی ندارید!\nاول یه ربات بسازید.",
            parse_mode="Markdown"
        )
        return
    
    text = "🎨 **پنل طراحی ربات**\n\n"
    text += "ربات‌های فعال شما:\n"
    for i, (bid, name) in enumerate(bots, 1):
        text += f"{i}. {name}\n"
    
    text += "\n👇 یک ربات رو انتخاب کن تا طراحی کنی:"
    
    # ذخیره مرحله
    save_temp(user_id, "design_select_bot")
    
    bot.send_message(
        message.chat.id,
        text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('design_'))
def design_callback(call):
    user_id = call.from_user.id
    action = call.data.replace('design_', '')
    
    if action == "back":
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
        return
    
    step, data = get_temp(user_id)
    
    if step == "design_select_bot" and "bot_id" not in data:
        # انتخاب ربات
        markup = types.InlineKeyboardMarkup(row_width=1)
        c.execute('''SELECT id, bot_name FROM user_bots WHERE user_id = ? AND status = 'running' ''', (user_id,))
        for bid, name in c.fetchall():
            btn = types.InlineKeyboardButton(name, callback_data=f"select_bot_{bid}")
            markup.add(btn)
        
        bot.edit_message_text(
            "🔍 لطفاً ربات مورد نظر رو انتخاب کن:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    
    elif action == "buttons":
        bot.send_message(
            call.message.chat.id,
            "🔘 **طراحی دکمه‌ها**\n\n"
            "هر خط یک دکمه جدید:\n"
            "مثال:\n"
            "🛍 محصولات\n"
            "📞 پشتیبانی\n"
            "ℹ️ درباره ما\n\n"
            "دکمه‌هات رو خط به خط بفرست:"
        )
        save_temp(user_id, "design_buttons_input", data)
    
    elif action == "welcome":
        msg = bot.send_message(
            call.message.chat.id,
            "📝 **متن خوش‌آمدگویی جدید رو بنویس:**\n\n"
            "مثال:\n"
            "سلام {name} عزیز!\n"
            "به ربات من خوش اومدی."
        )
        bot.register_next_step_handler(msg, save_welcome_text, data.get("bot_id"))

def save_welcome_text(message, bot_id):
    welcome = message.text.strip()
    user_id = message.from_user.id
    
    c.execute('''UPDATE user_bots SET welcome_text = ? WHERE id = ? AND user_id = ?''',
              (welcome, bot_id, user_id))
    conn.commit()
    
    bot.send_message(
        message.chat.id,
        "✅ متن خوش‌آمدگویی با موفقیت ذخیره شد!"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_bot_'))
def select_bot(call):
    bot_id = int(call.data.replace('select_bot_', ''))
    user_id = call.from_user.id
    
    step, data = get_temp(user_id)
    data["bot_id"] = bot_id
    save_temp(user_id, step, data)
    
    c.execute('''SELECT bot_name FROM user_bots WHERE id = ?''', (bot_id,))
    bot_name = c.fetchone()[0]
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔘 دکمه‌ها", callback_data="design_buttons")
    btn2 = types.InlineKeyboardButton("📝 متن", callback_data="design_welcome")
    btn3 = types.InlineKeyboardButton("📦 محصولات", callback_data="design_products")
    btn4 = types.InlineKeyboardButton("💰 پرداخت", callback_data="design_payment")
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.edit_message_text(
        f"✅ ربات '{bot_name}' انتخاب شد.\n\n"
        f"حالا می‌تونی طراحی کنی:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# ==================== ساخت ربات جدید ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot_start(message):
    msg = bot.send_message(
        message.chat.id,
        "🔑 **مرحله 1/4 - دریافت توکن**\n\n"
        "لطفاً توکن رباتت رو از @BotFather بگیر و بفرست:"
    )
    bot.register_next_step_handler(msg, get_bot_token)

def get_bot_token(message):
    token = message.text.strip()
    user_id = message.from_user.id
    
    try:
        test_bot = telebot.TeleBot(token)
        me = test_bot.get_me()
        
        save_temp(user_id, "new_bot_token", {"token": token, "bot_name": me.first_name, "username": me.username})
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ توکن معتبر است! ربات: {me.first_name}\n\n"
            f"**مرحله 2/4 - انتخاب قالب**\n\n"
            f"از بین قالب‌های زیر یکی رو انتخاب کن:"
        )
        
        show_templates(message.chat.id, user_id)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ توکن معتبر نیست!\n{str(e)}")

def show_templates(chat_id, user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    c.execute('''SELECT id, name, price FROM templates''')
    for tid, name, price in c.fetchall():
        price_text = "رایگان" if price == 0 else f"{price:,} تومان"
        btn = types.InlineKeyboardButton(f"{name} - {price_text}", callback_data=f"select_temp_{tid}")
        markup.add(btn)
    
    bot.send_message(
        chat_id,
        "📦 **قالب‌های آماده:**\n\n"
        "هر قالب رو که انتخاب کنی، رباتت با اون ساختار ساخته میشه.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_temp_'))
def select_template(call):
    template_id = int(call.data.replace('select_temp_', ''))
    user_id = call.from_user.id
    
    step, data = get_temp(user_id)
    data["template_id"] = template_id
    save_temp(user_id, step, data)
    
    c.execute('''SELECT name, price FROM templates WHERE id = ?''', (template_id,))
    temp_name, price = c.fetchone()
    
    if price > 0:
        # چک کردن موجودی
        c.execute('''SELECT balance FROM users WHERE user_id = ?''', (user_id,))
        balance = c.fetchone()[0]
        
        if balance < price:
            bot.send_message(
                call.message.chat.id,
                f"❌ موجودی کافی نیست!\n"
                f"موجودی: {balance:,} تومان\n"
                f"قیمت قالب: {price:,} تومان"
            )
            return
    
    msg = bot.send_message(
        call.message.chat.id,
        f"✅ قالب '{temp_name}' انتخاب شد.\n\n"
        f"**مرحله 3/4 - توضیحات ربات**\n\n"
        f"یه توضیح کوتاه درباره رباتت بنویس:"
    )
    bot.register_next_step_handler(msg, get_bot_description, data)

def get_bot_description(message, data):
    description = message.text.strip()
    user_id = message.from_user.id
    
    data["description"] = description
    save_temp(user_id, "new_bot_description", data)
    
    msg = bot.send_message(
        message.chat.id,
        f"✅ توضیحات ذخیره شد.\n\n"
        f"**مرحله 4/4 - متن خوش‌آمدگویی**\n\n"
        f"متن خوش‌آمدگویی رباتت رو بنویس:"
    )
    bot.register_next_step_handler(msg, get_bot_welcome, data)

def get_bot_welcome(message, data):
    welcome = message.text.strip()
    user_id = message.from_user.id
    
    token = data["token"]
    bot_name = data["bot_name"]
    username = data["username"]
    template_id = data["template_id"]
    description = data["description"]
    
    # ذخیره در دیتابیس
    c.execute('''INSERT INTO user_bots 
                 (user_id, bot_token, bot_name, bot_username, description, welcome_text, status, created_date) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (user_id, token, bot_name, username, description, welcome, 'stopped', datetime.now().isoformat()))
    bot_id = c.lastrowid
    conn.commit()
    
    # کم کردن هزینه قالب
    c.execute('''SELECT price FROM templates WHERE id = ?''', (template_id,))
    price = c.fetchone()[0]
    if price > 0:
        c.execute('''UPDATE users SET balance = balance - ? WHERE user_id = ?''', (price, user_id))
        conn.commit()
    
    # اجرای ربات
    pid = run_user_bot(user_id, token)
    if pid:
        c.execute('''UPDATE user_bots SET pid = ?, status = ? WHERE id = ?''', (pid, 'running', bot_id))
        conn.commit()
    
    clear_temp(user_id)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🎨 طراحی ربات", callback_data="design_main")
    btn2 = types.InlineKeyboardButton("📊 پنل مدیریت", callback_data=f"panel_{bot_id}")
    markup.add(btn1, btn2)
    
    bot.send_message(
        message.chat.id,
        f"✅ **ربات شما با موفقیت ساخته شد!** 🎉\n\n"
        f"🤖 نام: {bot_name}\n"
        f"🔗 لینک: https://t.me/{username}\n"
        f"📝 توضیحات: {description}\n"
        f"🔄 وضعیت: در حال اجرا\n\n"
        f"حالا می‌تونی با دکمه‌های زیر رباتت رو طراحی کنی:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==================== قالب‌های آماده ====================
@bot.message_handler(func=lambda m: m.text == '📦 قالب‌های آماده')
def show_templates_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    c.execute('''SELECT id, name, description, price FROM templates''')
    for tid, name, desc, price in c.fetchall():
        price_text = "رایگان" if price == 0 else f"{price:,} تومان"
        btn = types.InlineKeyboardButton(f"{name} - {price_text}", callback_data=f"template_info_{tid}")
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "📦 **قالب‌های آماده ساخت ربات**\n\n"
        "با هر قالب، رباتت با اون ساختار ساخته میشه و می‌تونی بعداً شخصی‌سازی کنی.",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('template_info_'))
def template_info(call):
    tid = int(call.data.replace('template_info_', ''))
    
    c.execute('''SELECT name, description, price FROM templates WHERE id = ?''', (tid,))
    name, desc, price = c.fetchone()
    
    price_text = "رایگان" if price == 0 else f"{price:,} تومان"
    
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("✅ استفاده از این قالب", callback_data=f"use_template_{tid}")
    markup.add(btn)
    
    bot.edit_message_text(
        f"📦 **{name}**\n\n"
        f"📝 {desc}\n"
        f"💰 قیمت: {price_text}\n\n"
        f"امکانات:\n"
        f"✅ پنل مدیریت\n"
        f"✅ دکمه‌های اختصاصی\n"
        f"✅ اتصال درگاه پرداخت\n"
        f"✅ آمار کاربران\n\n"
        f"می‌خوای از این قالب استفاده کنی؟",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# ==================== ربات‌های من ====================
@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    
    c.execute('''SELECT id, bot_name, bot_username, status, created_date FROM user_bots WHERE user_id = ?''', (user_id,))
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 شما هنوز رباتی نساخته‌اید!"
        )
        return
    
    for bid, name, username, status, date in bots:
        emoji = "🟢" if status == "running" else "🔴"
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("🎨 طراحی", callback_data=f"design_{bid}")
        btn2 = types.InlineKeyboardButton("📊 آمار", callback_data=f"stats_{bid}")
        btn3 = types.InlineKeyboardButton("🔄 راه‌اندازی", callback_data=f"restart_{bid}")
        btn4 = types.InlineKeyboardButton("⏹ توقف", callback_data=f"stop_{bid}")
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(
            message.chat.id,
            f"{emoji} **{name}**\n"
            f"🔗 https://t.me/{username}\n"
            f"📅 ساخته شده: {date[:10]}\n"
            f"🔄 وضعیت: {status}",
            reply_markup=markup,
            parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('design_'))
def design_bot_from_list(call):
    bid = int(call.data.replace('design_', ''))
    user_id = call.from_user.id
    
    c.execute('''SELECT bot_name FROM user_bots WHERE id = ? AND user_id = ?''', (bid, user_id))
    result = c.fetchone()
    
    if not result:
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!")
        return
    
    save_temp(user_id, "design_select_bot", {"bot_id": bid})
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔘 دکمه‌ها", callback_data="design_buttons")
    btn2 = types.InlineKeyboardButton("📝 متن", callback_data="design_welcome")
    btn3 = types.InlineKeyboardButton("📦 محصولات", callback_data="design_products")
    btn4 = types.InlineKeyboardButton("💰 پرداخت", callback_data="design_payment")
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.edit_message_text(
        f"🎨 طراحی ربات '{result[0]}'\n\n"
        f"یکی از بخش‌ها رو انتخاب کن:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# ==================== کیف پول ====================
@bot.message_handler(func=lambda m: m.text == '💰 کیف پول')
def wallet(message):
    user_id = message.from_user.id
    
    c.execute('''SELECT balance, plan, expire_date FROM users WHERE user_id = ?''', (user_id,))
    balance, plan, expire = c.fetchone()
    
    c.execute('''SELECT COUNT(*) FROM user_bots WHERE user_id = ?''', (user_id,))
    bots_count = c.fetchone()[0]
    
    expire_text = expire[:10] if expire else "ندارد"
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="add_balance")
    btn2 = types.InlineKeyboardButton("⭐ خرید اشتراک", callback_data="buy_plan")
    btn3 = types.InlineKeyboardButton("📊 تراکنش‌ها", callback_data="transactions")
    btn4 = types.InlineKeyboardButton("🎁 کد تخفیف", callback_data="coupon")
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(
        message.chat.id,
        f"💰 **کیف پول شما**\n\n"
        f"موجودی: {balance:,} تومان\n"
        f"پلن: {plan}\n"
        f"اعتبار تا: {expire_text}\n"
        f"ربات‌ها: {bots_count}\n\n"
        f"**قیمت قالب‌ها:**\n"
        f"• قالب رایگان: ۰ تومان\n"
        f"• قالب حرفه‌ای: ۵۰,۰۰۰ تومان\n"
        f"• قالب ویژه: ۱۰۰,۰۰۰ تومان\n\n"
        f"**اشتراک ماهانه:**\n"
        f"• نقره‌ای: ۱۰۰,۰۰۰ (۵ ربات)\n"
        f"• طلایی: ۲۵۰,۰۰۰ (۱۵ ربات)\n"
        f"• الماسی: ۵۰۰,۰۰۰ (نامحدود)",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == "add_balance")
def add_balance(call):
    msg = bot.send_message(
        call.message.chat.id,
        "💰 **مبلغ مورد نظر رو به تومان وارد کن:**\n"
        "(مثال: 50000 برای ۵۰ هزار تومان)\n\n"
        "حداقل مبلغ: ۱۰,۰۰۰ تومان"
    )
    bot.register_next_step_handler(msg, process_add_balance)

def process_add_balance(message):
    try:
        amount = int(message.text.replace(',', ''))
        
        if amount < 10000:
            bot.send_message(message.chat.id, "❌ حداقل مبلغ ۱۰,۰۰۰ تومان")
            return
        
        # اینجا لینک درگاه پرداخت
        payment_link = f"https://idpay.ir/pay?amount={amount}"
        
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("💳 پرداخت", url=payment_link)
        markup.add(btn)
        
        bot.send_message(
            message.chat.id,
            f"✅ لینک پرداخت برای {amount:,} تومان:\n\n"
            f"پس از پرداخت، موجودی شما شارژ میشه.",
            reply_markup=markup
        )
        
    except:
        bot.send_message(message.chat.id, "❌ لطفاً عدد معتبر وارد کن")

# ==================== راهنما ====================
@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def help_menu(message):
    help_text = (
        "📚 **راهنمای استفاده از استودیو طراحی ربات**\n\n"
        "**🤖 ساخت ربات جدید:**\n"
        "۱. از @BotFather توکن بگیر\n"
        "۲. توکن رو بفرست\n"
        "۳. قالب مورد نظر رو انتخاب کن\n"
        "۴. توضیحات و متن رو وارد کن\n\n"
        "**🎨 طراحی ربات:**\n"
        "• دکمه‌ها رو می‌تونی طراحی کنی\n"
        "• متن‌ها رو شخصی‌سازی کنی\n"
        "• محصولات رو مدیریت کنی\n"
        "• درگاه پرداخت وصل کنی\n\n"
        "**💰 قیمت‌ها:**\n"
        "• قالب رایگان: ۰ تومان\n"
        "• قالب حرفه‌ای: ۵۰,۰۰۰ تومان\n"
        "• اشتراک ماهانه نقره‌ای: ۱۰۰,۰۰۰ تومان\n"
        "• اشتراک ماهانه طلایی: ۲۵۰,۰۰۰ تومان\n\n"
        "**📞 پشتیبانی:**\n"
        "@support_bot"
    )
    
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# ==================== اجرا ====================
if __name__ == "__main__":
    print("🎨 استودیو طراحی ربات با موفقیت راه‌اندازی شد...")
    bot.infinity_polling()
