import telebot
from telebot import types
import sqlite3
import json
import os
import subprocess
import sys
import time
from datetime import datetime

# ==================== تنظیمات مسیر ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(USERS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

TOKEN = "7685135237:AAEmsHktRw9cEqrHTkCoPZk-fBimK7TDjOo"
bot = telebot.TeleBot(TOKEN)

# ==================== دیتابیس اصلی ====================
DB_PATH = os.path.join(BASE_DIR, 'bot_builder.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, username TEXT, joined_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_bots
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              bot_token TEXT UNIQUE,
              bot_name TEXT,
              welcome_text TEXT,
              btn_type TEXT,
              btn_name TEXT,
              btn_action TEXT,
              btn_link TEXT,
              payment_link TEXT,
              pid INTEGER,
              status TEXT,
              created_date TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS temp
             (user_id INTEGER PRIMARY KEY, token TEXT, welcome_text TEXT, 
              btn_type TEXT, btn_name TEXT, btn_action TEXT, btn_link TEXT)''')
conn.commit()

# ==================== توابع کمکی ====================
def get_user_folder(user_id):
    return os.path.join(USERS_DIR, str(user_id))

def run_user_bot(user_id, token):
    """اجرای ربات کاربر در یک پردازه جدا"""
    try:
        user_folder = get_user_folder(user_id)
        os.makedirs(user_folder, exist_ok=True)
        
        # ذخیره توکن
        with open(os.path.join(user_folder, "token.txt"), "w") as f:
            f.write(token)
        
        # اجرا
        process = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "user_bot.py"), str(user_id)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        return process.pid
    except Exception as e:
        print(f"خطا در اجرای ربات کاربر: {e}")
        return None

# ==================== هندلرهای اصلی ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, joined_date) 
                 VALUES (?, ?, ?)''', (user_id, username, datetime.now().isoformat()))
    conn.commit()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('🤖 ساخت ربات جدید')
    btn2 = types.KeyboardButton('✨ قابلیت‌های ویژه')
    btn3 = types.KeyboardButton('📋 ربات‌های من')
    btn4 = types.KeyboardButton('📚 راهنما')
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(
        message.chat.id,
        "🤖 **به ربات ساز حرفه‌ای خوش آمدید!**\n\n"
        "با این ربات می‌تونی در چند دقیقه ربات خودتو بسازی.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==================== مرحله 1: گرفتن توکن ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def step1_token(message):
    msg = bot.send_message(
        message.chat.id,
        "🔑 **مرحله 1 از 5**\n\n"
        "لطفاً توکن رباتت رو از @BotFather بگیر و بفرست:"
    )
    bot.register_next_step_handler(msg, step2_welcome)

def step2_welcome(message):
    token = message.text.strip()
    user_id = message.from_user.id
    
    try:
        # تست توکن
        test_bot = telebot.TeleBot(token)
        me = test_bot.get_me()
        bot_name = me.first_name
        
        c.execute('''INSERT OR REPLACE INTO temp (user_id, token) VALUES (?, ?)''', (user_id, token))
        conn.commit()
        
        msg = bot.send_message(
            message.chat.id,
            f"✅ توکن معتبر است! ربات: {bot_name}\n\n"
            "✍️ **مرحله 2 از 5**\n\n"
            "حالا متن خوش‌آمدگویی رباتت رو بنویس:"
        )
        bot.register_next_step_handler(msg, step3_button_type, token, bot_name)
        
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ توکن معتبر نیست! لطفاً دوباره امتحان کن.\n{str(e)}"
        )

def step3_button_type(message, token, bot_name):
    welcome_text = message.text.strip()
    user_id = message.from_user.id
    
    c.execute('''UPDATE temp SET welcome_text = ? WHERE user_id = ?''', (welcome_text, user_id))
    conn.commit()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔘 دکمه متنی", callback_data="btn_type_text")
    btn2 = types.InlineKeyboardButton("🔄 دکمه درون خطی", callback_data="btn_type_inline")
    markup.add(btn1, btn2)
    
    bot.send_message(
        message.chat.id,
        "🔘 **مرحله 3 از 5**\n\n"
        "چه نوع دکمه‌ای می‌خوای؟",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('btn_type_'))
def step4_button_name(call):
    btn_type = call.data.replace('btn_type_', '')
    user_id = call.from_user.id
    
    c.execute('''UPDATE temp SET btn_type = ? WHERE user_id = ?''', (btn_type, user_id))
    conn.commit()
    
    msg = bot.send_message(
        call.message.chat.id,
        "✍️ **مرحله 4 از 5**\n\n"
        "اسم دکمه رو بنویس:"
    )
    bot.register_next_step_handler(msg, step5_button_action)

def step5_button_action(message):
    btn_name = message.text.strip()
    user_id = message.from_user.id
    
    c.execute('''UPDATE temp SET btn_name = ? WHERE user_id = ?''', (btn_name, user_id))
    conn.commit()
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("💻 با کد نویسی", callback_data="action_code")
    btn2 = types.InlineKeyboardButton("🔗 لینک", callback_data="action_link")
    markup.add(btn1, btn2)
    
    bot.send_message(
        message.chat.id,
        f"🔘 **مرحله 5 از 5**\n\n"
        f"دکمه '{btn_name}' چه کاری انجام بده؟",
        reply_markup=markup
    )

# ==================== انتخاب action ====================
@bot.callback_query_handler(func=lambda call: call.data == "action_code")
def action_code(call):
    user_id = call.from_user.id
    c.execute('''UPDATE temp SET btn_action = 'code' WHERE user_id = ?''', (user_id,))
    conn.commit()
    
    bot.send_message(
        call.message.chat.id,
        "📄 **آپلود فایل**\n\n"
        "فایل پایتون خودت رو با اسم **m.py** آپلود کن:\n\n"
        "⚠️ دقت کن اسم فایل حتماً m.py باشه!"
    )

@bot.callback_query_handler(func=lambda call: call.data == "action_link")
def action_link(call):
    user_id = call.from_user.id
    c.execute('''UPDATE temp SET btn_action = 'link' WHERE user_id = ?''', (user_id,))
    conn.commit()
    
    msg = bot.send_message(
        call.message.chat.id,
        "🔗 لینک مورد نظر رو بفرست:"
    )
    bot.register_next_step_handler(msg, save_final_link)

def save_final_link(message):
    link = message.text.strip()
    user_id = message.from_user.id
    
    # گرفتن اطلاعات از temp
    c.execute('''SELECT token, welcome_text, btn_type, btn_name FROM temp WHERE user_id = ?''', (user_id,))
    row = c.fetchone()
    if not row:
        bot.send_message(message.chat.id, "❌ خطا! دوباره از اول شروع کن.")
        return
    
    token, welcome_text, btn_type, btn_name = row
    
    # تست توکن و گرفتن اسم ربات
    try:
        test_bot = telebot.TeleBot(token)
        me = test_bot.get_me()
        bot_name = me.first_name
        
        # اجرای ربات کاربر
        pid = run_user_bot(user_id, token)
        
        # ذخیره در user_bots
        c.execute('''INSERT INTO user_bots 
                     (user_id, bot_token, bot_name, welcome_text, btn_type, btn_name, btn_action, btn_link, pid, status, created_date) 
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, token, bot_name, welcome_text, btn_type, btn_name, 'link', link, pid, 'running', datetime.now().isoformat()))
        conn.commit()
        
        # پاک کردن temp
        c.execute('''DELETE FROM temp WHERE user_id = ?''', (user_id,))
        conn.commit()
        
        bot.send_message(
            message.chat.id,
            f"✅ **ربات شما با موفقیت ساخته شد!** 🎉\n\n"
            f"🤖 نام: {bot_name}\n"
            f"🔗 لینک: https://t.me/{me.username}\n"
            f"📝 متن: {welcome_text}\n"
            f"🔘 دکمه: {btn_name}\n"
            f"🔗 لینک دکمه: {link}\n"
            f"🔄 وضعیت: در حال اجرا\n\n"
            f"از بخش '✨ قابلیت‌های ویژه' می‌تونی امکانات بیشتری اضافه کنی.",
            parse_mode="Markdown"
        )
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا: {str(e)}")

# ==================== آپلود فایل ====================
@bot.message_handler(content_types=['document'])
def handle_file(message):
    try:
        file_name = message.document.file_name
        user_id = message.from_user.id
        
        if file_name != "m.py":
            bot.reply_to(message, "❌ اسم فایل باید m.py باشه!")
            return
        
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        user_folder = get_user_folder(user_id)
        os.makedirs(user_folder, exist_ok=True)
        file_path = os.path.join(user_folder, "m.py")
        
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        
        # گرفتن اطلاعات از temp
        c.execute('''SELECT token, welcome_text, btn_type, btn_name FROM temp WHERE user_id = ?''', (user_id,))
        result = c.fetchone()
        
        if result:
            token, welcome_text, btn_type, btn_name = result
            
            # تست توکن
            test_bot = telebot.TeleBot(token)
            me = test_bot.get_me()
            bot_name = me.first_name
            
            # اجرای ربات کاربر
            pid = run_user_bot(user_id, token)
            
            # ذخیره در user_bots
            c.execute('''INSERT INTO user_bots 
                         (user_id, bot_token, bot_name, welcome_text, btn_type, btn_name, btn_action, pid, status, created_date) 
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                      (user_id, token, bot_name, welcome_text, btn_type, btn_name, 'code', pid, 'running', datetime.now().isoformat()))
            conn.commit()
            
            # پاک کردن temp
            c.execute('''DELETE FROM temp WHERE user_id = ?''', (user_id,))
            conn.commit()
            
            bot.send_message(
                message.chat.id,
                f"✅ **فایل با موفقیت آپلود و ربات اجرا شد!**\n\n"
                f"🤖 نام: {bot_name}\n"
                f"🔗 لینک: https://t.me/{me.username}\n"
                f"🔄 وضعیت: در حال اجرا",
                parse_mode="Markdown"
            )
        
        # نمایش ۱۰ کتابخانه پیشنهادی
        markup = types.InlineKeyboardMarkup(row_width=2)
        libraries = [
            ("pyTelegramBotAPI", "telebot"),
            ("requests", "requests"),
            ("flask", "Flask"),
            ("django", "Django"),
            ("numpy", "numpy"),
            ("pandas", "pandas"),
            ("pillow", "Pillow"),
            ("beautifulsoup4", "bs4"),
            ("selenium", "selenium"),
            ("sqlalchemy", "SQLAlchemy")
        ]
        
        for lib_name, lib_pip in libraries:
            btn = types.InlineKeyboardButton(
                f"📦 {lib_name}",
                callback_data=f"install_{lib_pip}_{user_id}"
            )
            markup.add(btn)
        
        bot.send_message(
            message.chat.id,
            "📚 **۱۰ کتابخانه پیشنهادی:**\n"
            "کدوم رو می‌خوای نصب کنم؟",
            reply_markup=markup
        )
        
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('install_'))
def install_library(call):
    try:
        parts = call.data.split('_')
        lib_pip = parts[1]
        user_id = int(parts[2])
        
        bot.edit_message_text(
            f"🔄 در حال نصب {lib_pip}...",
            call.message.chat.id,
            call.message.message_id
        )
        
        # نصب کتابخانه
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", lib_pip],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            bot.send_message(
                call.message.chat.id,
                f"✅ کتابخانه {lib_pip} با موفقیت نصب شد!"
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f"❌ خطا در نصب:\n{result.stderr[:500]}"
            )
            
    except subprocess.TimeoutExpired:
        bot.send_message(call.message.chat.id, "❌ زمان نصب بیش از حد طول کشید.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

# ==================== قابلیت‌های ویژه ====================
@bot.message_handler(func=lambda m: m.text == '✨ قابلیت‌های ویژه')
def show_features(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔟 ۱۰ دکمه", callback_data="feature_10buttons")
    btn2 = types.InlineKeyboardButton("📢 پیام همگانی", callback_data="feature_broadcast")
    btn3 = types.InlineKeyboardButton("📊 آمار کاربران", callback_data="feature_stats")
    btn4 = types.InlineKeyboardButton("💰 درگاه پرداخت", callback_data="feature_payment")
    btn5 = types.InlineKeyboardButton("📦 محصولات", callback_data="feature_products")
    btn6 = types.InlineKeyboardButton("🔙 بازگشت", callback_data="feature_back")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    
    bot.send_message(
        message.chat.id,
        "✨ **قابلیت‌های ویژه:**\n\n"
        "🔟 **۱۰ دکمه** - تا ۱۰ دکمه به رباتت اضافه کن\n"
        "📢 **پیام همگانی** - به همه کاربرات پیام بفرست\n"
        "📊 **آمار کاربران** - تعداد کاربرات رو ببین\n"
        "💰 **درگاه پرداخت** - لینک درگاه پرداخت رو وصل کن\n"
        "📦 **محصولات** - محصولات خودتو اضافه کن\n\n"
        "👇 یکی رو انتخاب کن:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "feature_payment")
def feature_payment(call):
    msg = bot.send_message(
        call.message.chat.id,
        "💰 **وصل کردن درگاه پرداخت**\n\n"
        "لینک درگاه پرداختت رو بفرست:\n"
        "(مثال: https://zarinpal.com/merchant/123456)"
    )
    bot.register_next_step_handler(msg, save_payment)

def save_payment(message):
    payment_link = message.text.strip()
    user_id = message.from_user.id
    
    c.execute('''UPDATE user_bots SET payment_link = ? WHERE user_id = ?''', (payment_link, user_id))
    conn.commit()
    
    bot.send_message(
        message.chat.id,
        f"✅ درگاه پرداخت با موفقیت وصل شد!"
    )

@bot.callback_query_handler(func=lambda call: call.data == "feature_products")
def feature_products(call):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ افزودن محصول", callback_data="product_add")
    btn2 = types.InlineKeyboardButton("📋 لیست محصولات", callback_data="product_list")
    btn3 = types.InlineKeyboardButton("🗑 حذف محصول", callback_data="product_delete")
    btn4 = types.InlineKeyboardButton("🔙 بازگشت", callback_data="feature_back")
    markup.add(btn1, btn2, btn3, btn4)
    
    bot.send_message(
        call.message.chat.id,
        "📦 **مدیریت محصولات**",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "product_add")
def product_add(call):
    msg = bot.send_message(
        call.message.chat.id,
        "📦 اسم محصول رو بنویس:"
    )
    bot.register_next_step_handler(msg, product_get_price)

def product_get_price(message):
    product_name = message.text.strip()
    user_id = message.from_user.id
    
    msg = bot.send_message(
        message.chat.id,
        f"💰 قیمت {product_name} رو به تومان بنویس:"
    )
    bot.register_next_step_handler(msg, save_product, product_name)

def save_product(message, product_name):
    try:
        price = int(message.text.strip())
        user_id = message.from_user.id
        
        # دیتابیس مخصوص کاربر
        user_folder = get_user_folder(user_id)
        user_db = os.path.join(user_folder, "user_data.db")
        
        u_conn = sqlite3.connect(user_db)
        u_c = u_conn.cursor()
        
        u_c.execute('''CREATE TABLE IF NOT EXISTS products
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT,
                      price INTEGER,
                      created_date TEXT)''')
        
        u_c.execute('''INSERT INTO products (name, price, created_date)
                     VALUES (?, ?, ?)''',
                  (product_name, price, datetime.now().isoformat()))
        u_conn.commit()
        u_conn.close()
        
        bot.send_message(
            message.chat.id,
            f"✅ محصول '{product_name}' با قیمت {price:,} تومان اضافه شد!"
        )
    except:
        bot.send_message(message.chat.id, "❌ لطفاً عدد معتبر وارد کن.")

@bot.callback_query_handler(func=lambda call: call.data == "product_list")
def product_list(call):
    user_id = call.from_user.id
    user_folder = get_user_folder(user_id)
    user_db = os.path.join(user_folder, "user_data.db")
    
    if not os.path.exists(user_db):
        bot.send_message(call.message.chat.id, "📦 محصولی وجود ندارد.")
        return
    
    u_conn = sqlite3.connect(user_db)
    u_c = u_conn.cursor()
    u_c.execute('''SELECT name, price FROM products''')
    products = u_c.fetchall()
    u_conn.close()
    
    if not products:
        bot.send_message(call.message.chat.id, "📦 محصولی وجود ندارد.")
        return
    
    text = "📋 **لیست محصولات:**\n\n"
    for name, price in products:
        text += f"• {name} - {price:,} تومان\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "feature_stats")
def feature_stats(call):
    user_id = call.from_user.id
    
    c.execute('''SELECT COUNT(*) FROM user_bots WHERE user_id = ?''', (user_id,))
    bots_count = c.fetchone()[0]
    
    user_folder = get_user_folder(user_id)
    user_db = os.path.join(user_folder, "user_data.db")
    
    products_count = 0
    if os.path.exists(user_db):
        u_conn = sqlite3.connect(user_db)
        u_c = u_conn.cursor()
        u_c.execute('''SELECT COUNT(*) FROM products''')
        products_count = u_c.fetchone()[0]
        u_conn.close()
    
    bot.send_message(
        call.message.chat.id,
        f"📊 **آمار شما:**\n\n"
        f"🤖 تعداد ربات‌ها: {bots_count}\n"
        f"📦 تعداد محصولات: {products_count}"
    )

@bot.callback_query_handler(func=lambda call: call.data == "feature_back")
def feature_back(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    start(call.message)

# ==================== ربات‌های من ====================
@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    
    c.execute('''SELECT bot_name, bot_token, status, created_date FROM user_bots WHERE user_id = ?''', (user_id,))
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 شما هنوز رباتی نساخته‌اید!"
        )
        return
    
    text = "📋 **ربات‌های شما:**\n\n"
    for name, token, status, date in bots:
        emoji = "🟢" if status == "running" else "🔴"
        text += f"{emoji} **{name}**\n"
        text += f"   🔑 `{token[:20]}...`\n"
        text += f"   📅 {date[:10]}\n\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ==================== راهنما ====================
@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def help_message(message):
    help_text = (
        "📚 **راهنمای استفاده:**\n\n"
        "**🤖 ساخت ربات جدید:**\n"
        "1️⃣ از @BotFather توکن بگیر\n"
        "2️⃣ توکن رو اینجا بفرست\n"
        "3️⃣ متن خوش‌آمدگویی بنویس\n"
        "4️⃣ نوع دکمه رو انتخاب کن\n"
        "5️⃣ اسم دکمه رو بنویس\n"
        "6️⃣ کار دکمه رو مشخص کن\n\n"
        "**✨ قابلیت‌های ویژه:**\n"
        "• ۱۰ دکمه - اضافه کردن دکمه‌های بیشتر\n"
        "• پیام همگانی - ارسال پیام به همه\n"
        "• آمار کاربران - دیدن آمار\n"
        "• درگاه پرداخت - وصل کردن زرین‌پال\n"
        "• محصولات - اضافه کردن محصول\n\n"
        "**📞 پشتیبانی:**\n"
        "@support_bot"
    )
    
    bot.send_message(message.chat.id, help_text)

# ==================== اجرا ====================
if __name__ == "__main__":
    print(f"✅ ربات اصلی فعال شد... پوشه کاربران: {USERS_DIR}")
    bot.infinity_polling()
