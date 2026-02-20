import telebot
from telebot import types
import sqlite3
import json
import os
import subprocess
import sys
import time
import hashlib
from datetime import datetime
from threading import Thread
from queue import Queue
import shutil
import tempfile

# ==================== تنظیمات ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
BOTS_DIR = os.path.join(BASE_DIR, "bots")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

for dir_path in [USERS_DIR, BOTS_DIR, TEMP_DIR, LOGS_DIR]:
    os.makedirs(dir_path, exist_ok=True)

TOKEN = "8052349235:AAFSaJmYpl359BKrJTWC8O-u-dI9r2olEOQ"
bot = telebot.TeleBot(TOKEN)

# پاک کردن وب‌هوک
try:
    bot.delete_webhook()
except:
    pass

# ==================== دیتابیس اصلی ====================
DB_PATH = os.path.join(BASE_DIR, 'master.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA synchronous = NORMAL")
c = conn.cursor()

# جداول اصلی
c.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance INTEGER DEFAULT 0,
    plan TEXT DEFAULT 'free',
    bots_limit INTEGER DEFAULT 5,
    joined_date TEXT,
    last_active TEXT
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS user_bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bot_token TEXT UNIQUE,
    bot_name TEXT,
    bot_username TEXT,
    welcome_text TEXT DEFAULT 'به ربات من خوش آمدید!',
    status TEXT DEFAULT 'stopped',
    pid INTEGER,
    error_log TEXT,
    created_date TEXT,
    last_active TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS bot_buttons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    button_name TEXT,
    button_type TEXT,
    button_data TEXT,
    row_num INTEGER DEFAULT 0,
    col_num INTEGER DEFAULT 0,
    created_date TEXT,
    FOREIGN KEY(bot_id) REFERENCES user_bots(id) ON DELETE CASCADE
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS broadcast_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    message TEXT,
    status TEXT DEFAULT 'pending',
    sent_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    created_date TEXT,
    FOREIGN KEY(bot_id) REFERENCES user_bots(id) ON DELETE CASCADE
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS temp_data (
    user_id INTEGER PRIMARY KEY,
    step TEXT,
    data TEXT,
    expires INTEGER
)
''')

# ایندکس‌ها برای سرعت
c.execute('CREATE INDEX IF NOT EXISTS idx_user_bots_user_id ON user_bots(user_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_user_bots_status ON user_bots(status)')
c.execute('CREATE INDEX IF NOT EXISTS idx_bot_buttons_bot_id ON bot_buttons(bot_id)')
c.execute('CREATE INDEX IF NOT EXISTS idx_temp_expires ON temp_data(expires)')

conn.commit()

# ==================== توابع کمکی ====================
def get_user_folder(user_id):
    return os.path.join(USERS_DIR, str(user_id))

def get_bot_folder(bot_id):
    return os.path.join(BOTS_DIR, str(bot_id))

def save_temp(user_id, step, data=None, expire=3600):
    expire_time = int(time.time()) + expire
    data_json = json.dumps(data) if data else None
    
    c.execute('''
        INSERT OR REPLACE INTO temp_data (user_id, step, data, expires)
        VALUES (?, ?, ?, ?)
    ''', (user_id, step, data_json, expire_time))
    conn.commit()

def get_temp(user_id):
    c.execute('''
        SELECT step, data FROM temp_data 
        WHERE user_id = ? AND expires > ?
    ''', (user_id, int(time.time())))
    
    row = c.fetchone()
    if row:
        step, data = row
        return step, json.loads(data) if data else {}
    return None, {}

def clear_temp(user_id):
    c.execute('DELETE FROM temp_data WHERE user_id = ?', (user_id,))
    conn.commit()

def validate_python_code(code):
    try:
        compile(code, '<string>', 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)

def extract_token_from_code(code):
    import re
    patterns = [
        r'token\s*=\s*["\']([^"\']+)["\']',
        r'TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'API_TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'BOT_TOKEN\s*=\s*["\']([^"\']+)["\']'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, code)
        if match:
            return match.group(1)
    return None

def run_user_bot(bot_id, token):
    try:
        bot_folder = get_bot_folder(bot_id)
        os.makedirs(bot_folder, exist_ok=True)
        
        with open(os.path.join(bot_folder, "token.txt"), "w") as f:
            f.write(token)
        
        log_file = os.path.join(LOGS_DIR, f"bot_{bot_id}.log")
        
        process = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "user_bot.py"), str(bot_id)],
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        
        return process.pid
    except Exception as e:
        print(f"Error running bot {bot_id}: {e}")
        return None

# ==================== شروع ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    now = datetime.now().isoformat()
    
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, username, joined_date, last_active)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, now, now))
    
    c.execute('''
        UPDATE users SET last_active = ? WHERE user_id = ?
    ''', (now, user_id))
    conn.commit()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton('🤖 ساخت ربات جدید'),
        types.KeyboardButton('📋 ربات‌های من'),
        types.KeyboardButton('🔧 مدیریت ربات'),
        types.KeyboardButton('💰 کیف پول'),
        types.KeyboardButton('📚 راهنما')
    )
    
    bot.send_message(
        message.chat.id,
        "🚀 **به سکوی ساخت ربات خوش آمدید!**\n\n"
        "✅ آپلود فایل پایتون و اجرای خودکار\n"
        "✅ تشخیص خودکار توکن\n"
        "✅ دکمه‌های نامحدود\n"
        "✅ پیام همگانی\n"
        "✅ مقیاس‌پذیر تا میلیون‌ها ربات\n\n"
        "👇 یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==================== ساخت ربات با آپلود فایل ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot(message):
    msg = bot.send_message(
        message.chat.id,
        "📤 **آپلود فایل پایتون**\n\n"
        "فایل `.py` خود را ارسال کنید:\n\n"
        "✅ کد بررسی می‌شود\n"
        "✅ توکن استخراج می‌شود\n"
        "✅ اگر خطا نداشت، اجرا می‌شود"
    )
    bot.register_next_step_handler(msg, process_uploaded_file)

@bot.message_handler(content_types=['document'])
def process_uploaded_file(message):
    user_id = message.from_user.id
    
    try:
        if not message.document.file_name.endswith('.py'):
            bot.reply_to(message, "❌ فقط فایل پایتون (.py) مجاز است!")
            return
        
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        code = downloaded_file.decode('utf-8')
        
        # اعتبارسنجی کد
        is_valid, error = validate_python_code(code)
        if not is_valid:
            bot.reply_to(message, f"❌ خطای نحوی:\n```\n{error}\n```", parse_mode="Markdown")
            return
        
        # استخراج توکن
        token = extract_token_from_code(code)
        if not token:
            bot.reply_to(message, "❌ توکن در کد پیدا نشد!\nمثال: TOKEN = '123456:ABCdef'")
            return
        
        # تست توکن
        try:
            test_bot = telebot.TeleBot(token)
            me = test_bot.get_me()
            bot_name = me.first_name
            bot_username = me.username
        except Exception as e:
            bot.reply_to(message, f"❌ توکن معتبر نیست!\n{str(e)}")
            return
        
        # ذخیره در دیتابیس
        now = datetime.now().isoformat()
        c.execute('''
            INSERT INTO user_bots 
            (user_id, bot_token, bot_name, bot_username, status, created_date, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, token, bot_name, bot_username, 'starting', now, now))
        bot_id = c.lastrowid
        conn.commit()
        
        # ذخیره فایل
        bot_folder = get_bot_folder(bot_id)
        os.makedirs(bot_folder, exist_ok=True)
        
        with open(os.path.join(bot_folder, "bot.py"), "w", encoding='utf-8') as f:
            f.write(code)
        
        # اجرای ربات
        pid = run_user_bot(bot_id, token)
        
        if pid:
            c.execute('''
                UPDATE user_bots SET pid = ?, status = ? WHERE id = ?
            ''', (pid, 'running', bot_id))
            conn.commit()
            
            bot.send_message(
                message.chat.id,
                f"✅ **ربات با موفقیت اجرا شد!** 🎉\n\n"
                f"🤖 نام: {bot_name}\n"
                f"🔗 لینک: https://t.me/{bot_username}\n"
                f"🆔 آیدی: {bot_id}\n\n"
                f"برای مدیریت به بخش '🔧 مدیریت ربات' بروید.",
                parse_mode="Markdown"
            )
        else:
            c.execute('''
                UPDATE user_bots SET status = ? WHERE id = ?
            ''', ('error', bot_id))
            conn.commit()
            
            bot.send_message(
                message.chat.id,
                "❌ خطا در اجرای ربات!\n"
                "کد خود را بررسی کنید و دوباره تلاش کنید."
            )
            
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

# ==================== ربات‌های من ====================
@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    
    c.execute('''
        SELECT id, bot_name, bot_username, status, created_date 
        FROM user_bots WHERE user_id = ?
        ORDER BY id DESC
    ''', (user_id,))
    
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 شما هنوز رباتی نساخته‌اید!"
        )
        return
    
    for bot_id, name, username, status, date in bots:
        status_emoji = "🟢" if status == 'running' else "🔴" if status == 'error' else "🟡"
        
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("🔧 مدیریت", callback_data=f"manage_{bot_id}")
        markup.add(btn)
        
        bot.send_message(
            message.chat.id,
            f"{status_emoji} **{name}**\n"
            f"🔗 https://t.me/{username}\n"
            f"🆔 آیدی: {bot_id}\n"
            f"📅 ساخته شده: {date[:10]}\n"
            f"🔄 وضعیت: {status}",
            reply_markup=markup,
            parse_mode="Markdown"
        )

# ==================== مدیریت ربات ====================
@bot.message_handler(func=lambda m: m.text == '🔧 مدیریت ربات')
def manage_bot_select(message):
    user_id = message.from_user.id
    
    c.execute('''
        SELECT id, bot_name, status FROM user_bots 
        WHERE user_id = ? AND status = 'running'
        ORDER BY id DESC
    ''', (user_id,))
    
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 ربات فعالی برای مدیریت وجود ندارد!"
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for bot_id, name, status in bots:
        btn = types.InlineKeyboardButton(
            f"🤖 {name}",
            callback_data=f"manage_{bot_id}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "🔧 **مدیریت ربات**\n\n"
        "ربات مورد نظر را انتخاب کنید:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_'))
def manage_bot(call):
    bot_id = int(call.data.replace('manage_', ''))
    user_id = call.from_user.id
    
    c.execute('''
        SELECT bot_name, bot_username, welcome_text, status 
        FROM user_bots WHERE id = ? AND user_id = ?
    ''', (bot_id, user_id))
    
    result = c.fetchone()
    if not result:
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!")
        return
    
    name, username, welcome, status = result
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ دکمه جدید", callback_data=f"add_btn_{bot_id}"),
        types.InlineKeyboardButton("📋 دکمه‌ها", callback_data=f"list_btn_{bot_id}"),
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data=f"broadcast_{bot_id}"),
        types.InlineKeyboardButton("✍️ متن خوش‌آمدگویی", callback_data=f"welcome_{bot_id}"),
        types.InlineKeyboardButton("📊 آمار", callback_data=f"stats_{bot_id}"),
        types.InlineKeyboardButton("🔄 راه‌اندازی مجدد", callback_data=f"restart_{bot_id}"),
        types.InlineKeyboardButton("⏹ توقف", callback_data=f"stop_{bot_id}"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_menu")
    )
    
    bot.edit_message_text(
        f"🔧 **مدیریت ربات:** {name}\n"
        f"🔗 https://t.me/{username}\n"
        f"🔄 وضعیت: {status}\n"
        f"📝 متن فعلی: {welcome[:50]}...\n\n"
        f"یکی از گزینه‌ها را انتخاب کنید:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==================== افزودن دکمه ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('add_btn_'))
def add_button_start(call):
    bot_id = int(call.data.replace('add_btn_', ''))
    user_id = call.from_user.id
    
    save_temp(user_id, "add_button", {"bot_id": bot_id})
    
    msg = bot.send_message(
        call.message.chat.id,
        "🔘 **افزودن دکمه جدید**\n\n"
        "نام دکمه را وارد کنید:"
    )
    bot.register_next_step_handler(msg, add_button_name)

def add_button_name(message):
    user_id = message.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    data['name'] = message.text.strip()
    save_temp(user_id, step, data)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔗 لینک", callback_data="btn_type_link"),
        types.InlineKeyboardButton("📄 متن", callback_data="btn_type_text"),
        types.InlineKeyboardButton("📞 شماره تلفن", callback_data="btn_type_phone"),
        types.InlineKeyboardButton("📍 موقعیت", callback_data="btn_type_location"),
        types.InlineKeyboardButton("💻 اجرای کد", callback_data="btn_type_code")
    )
    
    bot.send_message(
        message.chat.id,
        f"🔘 دکمه '{data['name']}'\n\n"
        f"نوع دکمه را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('btn_type_'))
def add_button_type(call):
    btn_type = call.data.replace('btn_type_', '')
    user_id = call.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    data['type'] = btn_type
    save_temp(user_id, step, data)
    
    messages = {
        'link': "🔗 لینک مورد نظر را ارسال کنید:",
        'text': "📄 متنی که با کلیک ارسال شود را بنویسید:",
        'phone': "📞 شماره تلفن را وارد کنید:",
        'location': "📍 موقعیت مکانی را ارسال کنید:",
        'code': "💻 کد پایتون را ارسال کنید:"
    }
    
    msg = bot.send_message(
        call.message.chat.id,
        messages.get(btn_type, "مقدار را وارد کنید:")
    )
    bot.register_next_step_handler(msg, add_button_value)

def add_button_value(message):
    user_id = message.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    value = message.text.strip()
    bot_id = data['bot_id']
    name = data['name']
    btn_type = data['type']
    
    c.execute('''
        INSERT INTO bot_buttons (bot_id, button_name, button_type, button_data, created_date)
        VALUES (?, ?, ?, ?, ?)
    ''', (bot_id, name, btn_type, value, datetime.now().isoformat()))
    conn.commit()
    
    clear_temp(user_id)
    
    bot.send_message(
        message.chat.id,
        f"✅ دکمه '{name}' با موفقیت اضافه شد!"
    )

# ==================== لیست دکمه‌ها ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('list_btn_'))
def list_buttons(call):
    bot_id = int(call.data.replace('list_btn_', ''))
    
    c.execute('''
        SELECT id, button_name, button_type, button_data 
        FROM bot_buttons WHERE bot_id = ?
        ORDER BY id
    ''', (bot_id,))
    
    buttons = c.fetchall()
    
    if not buttons:
        bot.send_message(
            call.message.chat.id,
            "📋 هیچ دکمه‌ای تعریف نشده است!"
        )
        return
    
    text = "📋 **دکمه‌های تعریف شده:**\n\n"
    for bid, name, btype, bdata in buttons:
        text += f"🆔 {bid} - {name}\n"
        text += f"   نوع: {btype}\n"
        text += f"   مقدار: {bdata[:50]}...\n\n"
    
    bot.send_message(call.message.chat.id, text, parse_mode="Markdown")

# ==================== پیام همگانی ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast_'))
def broadcast_start(call):
    bot_id = int(call.data.replace('broadcast_', ''))
    user_id = call.from_user.id
    
    save_temp(user_id, "broadcast", {"bot_id": bot_id})
    
    msg = bot.send_message(
        call.message.chat.id,
        "📢 **ارسال پیام همگانی**\n\n"
        "متن پیام را وارد کنید:"
    )
    bot.register_next_step_handler(msg, broadcast_message)

def broadcast_message(message):
    user_id = message.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    text = message.text.strip()
    bot_id = data['bot_id']
    
    # دریافت تعداد کاربران
    bot_folder = get_bot_folder(bot_id)
    db_file = os.path.join(bot_folder, "user_data.db")
    
    users_count = 0
    if os.path.exists(db_file):
        try:
            b_conn = sqlite3.connect(db_file)
            b_c = b_conn.cursor()
            b_c.execute('SELECT COUNT(*) FROM users')
            users_count = b_c.fetchone()[0]
            b_conn.close()
        except:
            pass
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ ارسال", callback_data=f"send_broadcast_{bot_id}"),
        types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_broadcast")
    )
    
    data['text'] = text
    save_temp(user_id, step, data)
    
    bot.send_message(
        message.chat.id,
        f"📢 **پیام شما:**\n\n{text}\n\n"
        f"👥 تعداد کاربران: {users_count}\n\n"
        f"برای ارسال تأیید کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('send_broadcast_'))
def send_broadcast(call):
    bot_id = int(call.data.replace('send_broadcast_', ''))
    user_id = call.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    text = data['text']
    
    bot.edit_message_text(
        "🔄 در حال ارسال پیام...",
        call.message.chat.id,
        call.message.message_id
    )
    
    # دریافت توکن ربات
    c.execute('SELECT bot_token FROM user_bots WHERE id = ?', (bot_id,))
    token = c.fetchone()[0]
    
    # دریافت کاربران
    bot_folder = get_bot_folder(bot_id)
    db_file = os.path.join(bot_folder, "user_data.db")
    
    if not os.path.exists(db_file):
        bot.send_message(call.message.chat.id, "❌ دیتابیس کاربران پیدا نشد!")
        return
    
    try:
        b_conn = sqlite3.connect(db_file)
        b_c = b_conn.cursor()
        b_c.execute('SELECT user_id FROM users')
        users = b_c.fetchall()
        b_conn.close()
        
        total = len(users)
        sent = 0
        failed = 0
        
        b = telebot.TeleBot(token)
        
        for uid in users:
            try:
                b.send_message(uid[0], text)
                sent += 1
            except:
                failed += 1
            
            if sent % 10 == 0:
                time.sleep(0.5)
        
        clear_temp(user_id)
        
        bot.send_message(
            call.message.chat.id,
            f"✅ **پیام همگانی با موفقیت ارسال شد!**\n\n"
            f"📊 آمار:\n"
            f"✅ موفق: {sent}\n"
            f"❌ ناموفق: {failed}\n"
            f"👥 مجموع: {total}"
        )
        
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "cancel_broadcast")
def cancel_broadcast(call):
    user_id = call.from_user.id
    clear_temp(user_id)
    bot.edit_message_text(
        "❌ ارسال لغو شد.",
        call.message.chat.id,
        call.message.message_id
    )

# ==================== سایر هندلرها ====================
@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    bot.delete_message(call.message.chat.id, call.message.message_id)
    start(call.message)

@bot.message_handler(func=lambda m: m.text == '💰 کیف پول')
def wallet(message):
    user_id = message.from_user.id
    
    c.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    balance = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM user_bots WHERE user_id = ?', (user_id,))
    bots_count = c.fetchone()[0]
    
    bot.send_message(
        message.chat.id,
        f"💰 **کیف پول شما**\n\n"
        f"موجودی: {balance:,} تومان\n"
        f"تعداد ربات‌ها: {bots_count}\n"
        f"سقف ربات: نامحدود\n\n"
        f"💳 افزایش موجودی به زودی...",
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def help_message(message):
    help_text = (
        "📚 **راهنمای استفاده**\n\n"
        "**🤖 ساخت ربات جدید:**\n"
        "1. فایل پایتون خود را آپلود کنید\n"
        "2. توکن باید در کد باشد\n"
        "3. ربات به صورت خودکار اجرا می‌شود\n\n"
        "**🔧 مدیریت ربات:**\n"
        "• افزودن دکمه‌های نامحدود\n"
        "• ارسال پیام همگانی\n"
        "• تغییر متن خوش‌آمدگویی\n"
        "• مشاهده آمار\n\n"
        "**💡 نکات مهم:**\n"
        "• فایل باید .py باشد\n"
        "• توکن حتماً در کد تعریف شود\n"
        "• کتابخانه‌های مورد نیاز نصب شود\n\n"
        "**📞 پشتیبانی:**\n"
        "@support_bot"
    )
    
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

# ==================== پاک‌سازی ====================
def cleanup_temp():
    c.execute('DELETE FROM temp_data WHERE expires < ?', (int(time.time()),))
    conn.commit()
    threading.Timer(3600, cleanup_temp).start()

cleanup_temp()

# ==================== اجرا ====================
if __name__ == "__main__":
    print("🚀 ربات اصلی با موفقیت راه‌اندازی شد...")
    print(f"📁 پوشه کاربران: {USERS_DIR}")
    print(f"📁 پوشه ربات‌ها: {BOTS_DIR}")
    
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        print(f"❌ خطا: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
