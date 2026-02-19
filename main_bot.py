import telebot
from telebot import types
import sqlite3
import json
import os
import subprocess
import sys
import time
import hashlib
import redis
import threading
from queue import Queue
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# ==================== تنظیمات پیشرفته ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
BOTS_DIR = os.path.join(BASE_DIR, "bots")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
QUEUE_DIR = os.path.join(BASE_DIR, "queue")
os.makedirs(USERS_DIR, exist_ok=True)
os.makedirs(BOTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(QUEUE_DIR, exist_ok=True)

TOKEN = "7956758689:AAH3JZ3kzBybVqPwRZ_pXlyA7Pez0n3BZ0o"
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

# ==================== Redis برای کش و صف ====================
try:
    r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    r.ping()
    REDIS_AVAILABLE = True
except:
    REDIS_AVAILABLE = False
    print("⚠️ Redis در دسترس نیست، از حافظه محلی استفاده می‌شود")

# ==================== Thread Pool برای پردازش موازی ====================
executor = ThreadPoolExecutor(max_workers=10)
process_executor = ProcessPoolExecutor(max_workers=4)
task_queue = Queue()

# ==================== دیتابیس اصلی ====================
DB_PATH = os.path.join(BASE_DIR, 'master_bot.db')
conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, 
              username TEXT,
              email TEXT,
              phone TEXT,
              balance BIGINT DEFAULT 0,
              plan TEXT DEFAULT 'free',
              bots_limit INTEGER DEFAULT 5,
              expire_date TEXT,
              joined_date TEXT,
              last_active TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_bots
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              bot_token TEXT UNIQUE,
              bot_name TEXT,
              bot_username TEXT,
              description TEXT,
              welcome_text TEXT,
              buttons TEXT,
              inline_buttons TEXT,
              admins TEXT,
              products TEXT,
              payment_gateway TEXT,
              webhook_url TEXT,
              pid INTEGER,
              port INTEGER,
              status TEXT,
              error_log TEXT,
              created_date TEXT,
              last_active TEXT,
              INDEX idx_user_id (user_id),
              INDEX idx_status (status))''')

c.execute('''CREATE TABLE IF NOT EXISTS bot_buttons
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              bot_id INTEGER,
              button_name TEXT,
              button_type TEXT,
              button_action TEXT,
              button_data TEXT,
              row_number INTEGER,
              col_number INTEGER,
              created_date TEXT,
              FOREIGN KEY(bot_id) REFERENCES user_bots(id),
              INDEX idx_bot_id (bot_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS broadcast_queue
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              bot_id INTEGER,
              message TEXT,
              media TEXT,
              buttons TEXT,
              status TEXT DEFAULT 'pending',
              sent_count INTEGER DEFAULT 0,
              total_count INTEGER DEFAULT 0,
              created_date TEXT,
              INDEX idx_status (status))''')

c.execute('''CREATE TABLE IF NOT EXISTS templates
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              description TEXT,
              category TEXT,
              price INTEGER,
              code TEXT,
              downloads INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS temp
             (user_id INTEGER PRIMARY KEY, 
              step TEXT,
              data TEXT,
              expires INTEGER)''')
conn.commit()

# ==================== توابع کمکی ====================
def get_user_folder(user_id):
    return os.path.join(USERS_DIR, str(user_id))

def get_bot_folder(bot_id):
    return os.path.join(BOTS_DIR, str(bot_id))

def save_temp(user_id, step, data=None, expire=3600):
    data_str = json.dumps(data) if data else None
    expire_time = int(time.time()) + expire
    if REDIS_AVAILABLE:
        r.setex(f"temp:{user_id}", expire, json.dumps({"step": step, "data": data}))
    else:
        c.execute('''INSERT OR REPLACE INTO temp (user_id, step, data, expires) 
                     VALUES (?, ?, ?, ?)''', (user_id, step, data_str, expire_time))
        conn.commit()

def get_temp(user_id):
    if REDIS_AVAILABLE:
        data = r.get(f"temp:{user_id}")
        if data:
            return json.loads(data)["step"], json.loads(data)["data"]
    else:
        c.execute('''SELECT step, data FROM temp WHERE user_id = ? AND expires > ?''', 
                  (user_id, int(time.time())))
        row = c.fetchone()
        if row:
            step, data = row
            return step, json.loads(data) if data else {}
    return None, {}

def clear_temp(user_id):
    if REDIS_AVAILABLE:
        r.delete(f"temp:{user_id}")
    else:
        c.execute('''DELETE FROM temp WHERE user_id = ?''', (user_id,))
        conn.commit()

def get_available_port():
    """پیدا کردن پورت آزاد برای ربات جدید"""
    import socket
    from contextlib import closing
    
    for port in range(8000, 9000):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            if sock.connect_ex(('localhost', port)) != 0:
                return port
    return None

def validate_python_code(code):
    """اعتبارسنجی کد پایتون بدون اجرا"""
    try:
        compile(code, '<string>', 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)

def extract_token_from_code(code):
    """استخراج توکن از کد پایتون"""
    import re
    patterns = [
        r'token\s*=\s*["\']([^"\']+)["\']',
        r'TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'api_token\s*=\s*["\']([^"\']+)["\']',
        r'bot_token\s*=\s*["\']([^"\']+)["\']'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, code)
        if match:
            return match.group(1)
    return None

def run_user_bot(bot_id, token, code=None):
    """اجرای ربات کاربر در پردازه جدا با مانیتورینگ"""
    try:
        bot_folder = get_bot_folder(bot_id)
        os.makedirs(bot_folder, exist_ok=True)
        
        # ذخیره توکن
        with open(os.path.join(bot_folder, "token.txt"), "w") as f:
            f.write(token)
        
        # اگر کد داده شده، ذخیره کن
        if code:
            with open(os.path.join(bot_folder, "bot.py"), "w", encoding='utf-8') as f:
                f.write(code)
        
        # گرفتن پورت آزاد
        port = get_available_port()
        
        # اجرا با nohup برای پایدار بودن
        log_file = os.path.join(LOGS_DIR, f"bot_{bot_id}.log")
        process = subprocess.Popen(
            [sys.executable, os.path.join(BASE_DIR, "user_bot_runner.py"), str(bot_id), str(port)],
            stdout=open(log_file, 'w'),
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True
        )
        
        return process.pid, port
    except Exception as e:
        print(f"خطا در اجرای ربات {bot_id}: {e}")
        return None, None

# ==================== منوی اصلی ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    now = datetime.now().isoformat()
    
    c.execute('''INSERT OR IGNORE INTO users (user_id, username, joined_date, last_active) 
                 VALUES (?, ?, ?, ?)''', (user_id, username, now, now))
    c.execute('''UPDATE users SET last_active = ? WHERE user_id = ?''', (now, user_id))
    conn.commit()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn1 = types.KeyboardButton('🤖 ساخت ربات با آپلود فایل')
    btn2 = types.KeyboardButton('🎨 طراحی ربات')
    btn3 = types.KeyboardButton('📋 ربات‌های من')
    btn4 = types.KeyboardButton('🔧 پنل مدیریت ربات')
    btn5 = types.KeyboardButton('📊 آمار کلی')
    btn6 = types.KeyboardButton('💰 کیف پول')
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    
    # آمار کاربر
    c.execute('''SELECT COUNT(*) FROM user_bots WHERE user_id = ?''', (user_id,))
    bots_count = c.fetchone()[0]
    
    bot.send_message(
        message.chat.id,
        f"🚀 **به سکوی ابری ساخت ربات خوش آمدید!**\n\n"
        f"👤 کاربر: {username}\n"
        f"🤖 تعداد ربات‌ها: {bots_count}\n\n"
        f"✨ امکانات:\n"
        f"✅ آپلود فایل پایتون و اجرای خودکار\n"
        f"✅ تشخیص خودکار توکن\n"
        f"✅ پنل مدیریت با دکمه‌های نامحدود\n"
        f"✅ ارسال پیام همگانی به میلیون‌ها کاربر\n"
        f"✅ مقیاس‌پذیر تا میلیون‌ها ربات\n\n"
        f"👇 یکی از گزینه‌ها رو انتخاب کن:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==================== آپلود فایل پایتون ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات با آپلود فایل')
def upload_file_step(message):
    msg = bot.send_message(
        message.chat.id,
        "📤 **آپلود فایل پایتون**\n\n"
        "فایل `.py` خودت رو بفرست:\n\n"
        "✅ کد بررسی می‌شود\n"
        "✅ توکن به صورت خودکار استخراج می‌شود\n"
        "✅ اگر خطا نداشت، اجرا می‌شود\n\n"
        "⚠️ نکته: توکن باید توی کد باشه"
    )
    bot.register_next_step_handler(msg, process_uploaded_file)

@bot.message_handler(content_types=['document'])
def process_uploaded_file(message):
    try:
        user_id = message.from_user.id
        file_name = message.document.file_name
        
        if not file_name.endswith('.py'):
            bot.reply_to(message, "❌ فقط فایل پایتون (.py) مجاز است!")
            return
        
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        code = downloaded_file.decode('utf-8')
        
        # اعتبارسنجی کد
        is_valid, error = validate_python_code(code)
        if not is_valid:
            bot.reply_to(message, f"❌ خطای نحوی در کد:\n```\n{error}\n```", parse_mode="Markdown")
            return
        
        # استخراج توکن
        token = extract_token_from_code(code)
        if not token:
            bot.reply_to(message, "❌ توکن در کد پیدا نشد!\nتوکن باید به صورت token = '...' تعریف شده باشد.")
            return
        
        # تست توکن
        try:
            test_bot = telebot.TeleBot(token)
            me = test_bot.get_me()
            bot_name = me.first_name
            bot_username = me.username
        except:
            bot.reply_to(message, "❌ توکن معتبر نیست!")
            return
        
        # ذخیره در دیتابیس
        c.execute('''INSERT INTO user_bots 
                     (user_id, bot_token, bot_name, bot_username, status, created_date) 
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (user_id, token, bot_name, bot_username, 'starting', datetime.now().isoformat()))
        bot_id = c.lastrowid
        conn.commit()
        
        # ایجاد پوشه و ذخیره کد
        bot_folder = get_bot_folder(bot_id)
        os.makedirs(bot_folder, exist_ok=True)
        
        with open(os.path.join(bot_folder, "bot.py"), "w", encoding='utf-8') as f:
            f.write(code)
        
        # اجرای ربات
        pid, port = run_user_bot(bot_id, token, code)
        
        if pid:
            c.execute('''UPDATE user_bots SET pid = ?, port = ?, status = ? WHERE id = ?''',
                      (pid, port, 'running', bot_id))
            conn.commit()
            
            bot.send_message(
                message.chat.id,
                f"✅ **ربات با موفقیت اجرا شد!** 🎉\n\n"
                f"🤖 نام: {bot_name}\n"
                f"🔗 لینک: https://t.me/{bot_username}\n"
                f"🆔 آیدی: {bot_id}\n"
                f"🔌 پورت: {port}\n"
                f"🔄 وضعیت: در حال اجرا\n\n"
                f"برای مدیریت به بخش '🔧 پنل مدیریت ربات' برو.",
                parse_mode="Markdown"
            )
        else:
            c.execute('''UPDATE user_bots SET status = ? WHERE id = ?''', ('error', bot_id))
            conn.commit()
            
            bot.send_message(
                message.chat.id,
                f"❌ خطا در اجرای ربات!\n"
                f"کدت رو چک کن و دوباره امتحان کن."
            )
            
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

# ==================== پنل مدیریت ربات ====================
@bot.message_handler(func=lambda m: m.text == '🔧 پنل مدیریت ربات')
def bot_management_panel(message):
    user_id = message.from_user.id
    
    c.execute('''SELECT id, bot_name, status FROM user_bots WHERE user_id = ?''', (user_id,))
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 شما رباتی ندارید!\nاول یه ربات بسازید."
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for bid, name, status in bots:
        emoji = "🟢" if status == "running" else "🔴"
        btn = types.InlineKeyboardButton(
            f"{emoji} {name}",
            callback_data=f"manage_bot_{bid}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "🔧 **پنل مدیریت ربات‌ها**\n\n"
        "ربات مورد نظر برای مدیریت رو انتخاب کن:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('manage_bot_'))
def manage_bot(call):
    bot_id = int(call.data.replace('manage_bot_', ''))
    user_id = call.from_user.id
    
    c.execute('''SELECT bot_name, bot_username, status, port FROM user_bots WHERE id = ? AND user_id = ?''',
              (bot_id, user_id))
    result = c.fetchone()
    
    if not result:
        bot.answer_callback_query(call.id, "❌ دسترسی ندارید!")
        return
    
    name, username, status, port = result
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("➕ افزودن دکمه", callback_data=f"add_button_{bot_id}")
    btn2 = types.InlineKeyboardButton("📋 دکمه‌ها", callback_data=f"list_buttons_{bot_id}")
    btn3 = types.InlineKeyboardButton("📢 پیام همگانی", callback_data=f"broadcast_{bot_id}")
    btn4 = types.InlineKeyboardButton("📊 آمار", callback_data=f"bot_stats_{bot_id}")
    btn5 = types.InlineKeyboardButton("📦 محصولات", callback_data=f"products_{bot_id}")
    btn6 = types.InlineKeyboardButton("💰 درگاه", callback_data=f"payment_{bot_id}")
    btn7 = types.InlineKeyboardButton("🔄 راه‌اندازی مجدد", callback_data=f"restart_{bot_id}")
    btn8 = types.InlineKeyboardButton("⏹ توقف", callback_data=f"stop_{bot_id}")
    btn9 = types.InlineKeyboardButton("📝 لاگ خطاها", callback_data=f"logs_{bot_id}")
    btn10 = types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_manage")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6, btn7, btn8, btn9, btn10)
    
    bot.edit_message_text(
        f"🔧 **مدیریت ربات:** {name}\n"
        f"🔗 https://t.me/{username}\n"
        f"🔄 وضعیت: {status}\n"
        f"🔌 پورت: {port}\n\n"
        f"یکی از گزینه‌ها رو انتخاب کن:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

# ==================== افزودن دکمه نامحدود ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('add_button_'))
def add_button_start(call):
    bot_id = int(call.data.replace('add_button_', ''))
    user_id = call.from_user.id
    
    save_temp(user_id, "add_button", {"bot_id": bot_id, "step": "name"})
    
    msg = bot.send_message(
        call.message.chat.id,
        "🔘 **افزودن دکمه جدید**\n\n"
        "اسم دکمه رو بنویس:\n"
        "(مثال: 🛍 محصولات)"
    )
    bot.register_next_step_handler(msg, add_button_name)

def add_button_name(message):
    user_id = message.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    data["name"] = message.text.strip()
    data["step"] = "type"
    save_temp(user_id, step, data)
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("🔗 لینک", callback_data="btn_type_link")
    btn2 = types.InlineKeyboardButton("📄 متن", callback_data="btn_type_text")
    btn3 = types.InlineKeyboardButton("📞 شماره", callback_data="btn_type_phone")
    btn4 = types.InlineKeyboardButton("📍 مکان", callback_data="btn_type_location")
    btn5 = types.InlineKeyboardButton("🔄 پرس و جو", callback_data="btn_type_query")
    btn6 = types.InlineKeyboardButton("💻 کد", callback_data="btn_type_code")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    
    bot.send_message(
        message.chat.id,
        f"🔘 دکمه '{data['name']}'\n\n"
        f"نوع دکمه رو انتخاب کن:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('btn_type_'))
def add_button_type(call):
    btn_type = call.data.replace('btn_type_', '')
    user_id = call.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    data["type"] = btn_type
    data["step"] = "action"
    save_temp(user_id, step, data)
    
    if btn_type == "link":
        msg = bot.send_message(
            call.message.chat.id,
            "🔗 لینک مورد نظر رو بفرست:\n"
            "(مثال: https://t.me/example)"
        )
        bot.register_next_step_handler(msg, save_button_action)
    
    elif btn_type == "text":
        msg = bot.send_message(
            call.message.chat.id,
            "📄 متنی که با کلیک ارسال بشه رو بنویس:"
        )
        bot.register_next_step_handler(msg, save_button_action)
    
    elif btn_type == "code":
        msg = bot.send_message(
            call.message.chat.id,
            "💻 کد پایتون رو بفرست (بدون نیاز به توکن):"
        )
        bot.register_next_step_handler(msg, save_button_action)
    
    else:
        msg = bot.send_message(
            call.message.chat.id,
            f"مقدار مورد نظر رو بفرست:"
        )
        bot.register_next_step_handler(msg, save_button_action)

def save_button_action(message):
    user_id = message.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    action_data = message.text.strip()
    bot_id = data["bot_id"]
    name = data["name"]
    btn_type = data["type"]
    
    # ذخیره در دیتابیس
    c.execute('''INSERT INTO bot_buttons 
                 (bot_id, button_name, button_type, button_action, button_data, created_date) 
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (bot_id, name, btn_type, action_data, json.dumps(data), datetime.now().isoformat()))
    conn.commit()
    
    clear_temp(user_id)
    
    bot.send_message(
        message.chat.id,
        f"✅ دکمه '{name}' با موفقیت اضافه شد!\n"
        f"نوع: {btn_type}\n"
        f"مقدار: {action_data[:50]}..."
    )

# ==================== پیام همگانی ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast_'))
def broadcast_start(call):
    bot_id = int(call.data.replace('broadcast_', ''))
    user_id = call.from_user.id
    
    save_temp(user_id, "broadcast", {"bot_id": bot_id})
    
    msg = bot.send_message(
        call.message.chat.id,
        "📢 **ارسال پیام همگانی**\n\n"
        "متن پیام رو بنویس:"
    )
    bot.register_next_step_handler(msg, broadcast_message)

def broadcast_message(message):
    user_id = message.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    text = message.text.strip()
    bot_id = data["bot_id"]
    
    # دریافت تعداد کاربران ربات
    bot_folder = get_bot_folder(bot_id)
    db_file = os.path.join(bot_folder, "user_data.db")
    
    if os.path.exists(db_file):
        b_conn = sqlite3.connect(db_file)
        b_c = b_conn.cursor()
        b_c.execute('''SELECT COUNT(*) FROM users''')
        users_count = b_c.fetchone()[0]
        b_conn.close()
    else:
        users_count = 0
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("✅ ارسال", callback_data=f"broadcast_send_{bot_id}")
    btn2 = types.InlineKeyboardButton("➕ افزودن دکمه", callback_data=f"broadcast_button_{bot_id}")
    btn3 = types.InlineKeyboardButton("🖼 افزودن عکس", callback_data=f"broadcast_photo_{bot_id}")
    btn4 = types.InlineKeyboardButton("🔙 انصراف", callback_data="broadcast_cancel")
    markup.add(btn1, btn2, btn3, btn4)
    
    data["text"] = text
    save_temp(user_id, step, data)
    
    bot.send_message(
        message.chat.id,
        f"📢 **پیام شما:**\n\n{text}\n\n"
        f"👥 تعداد کاربران: {users_count}\n\n"
        f"برای ارسال تایید کن:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('broadcast_send_'))
def broadcast_send(call):
    bot_id = int(call.data.replace('broadcast_send_', ''))
    user_id = call.from_user.id
    step, data = get_temp(user_id)
    
    if not data:
        return
    
    text = data["text"]
    
    bot.edit_message_text(
        "🔄 در حال ارسال پیام به کاربران...\n"
        "این عملیات ممکن است چند دقیقه طول بکشد.",
        call.message.chat.id,
        call.message.message_id
    )
    
    # ارسال در thread جدا
    executor.submit(process_broadcast, bot_id, text, call.message.chat.id)

def process_broadcast(bot_id, text, chat_id):
    """پردازش پیام همگانی در thread جدا"""
    try:
        bot_folder = get_bot_folder(bot_id)
        db_file = os.path.join(bot_folder, "user_data.db")
        
        if not os.path.exists(db_file):
            bot.send_message(chat_id, "❌ دیتابیس کاربران پیدا نشد!")
            return
        
        b_conn = sqlite3.connect(db_file)
        b_c = b_conn.cursor()
        b_c.execute('''SELECT user_id FROM users''')
        users = b_c.fetchall()
        b_conn.close()
        
        total = len(users)
        sent = 0
        failed = 0
        
        # دریافت توکن ربات
        c.execute('''SELECT bot_token FROM user_bots WHERE id = ?''', (bot_id,))
        token = c.fetchone()[0]
        b = telebot.TeleBot(token)
        
        for user_id in users:
            try:
                b.send_message(user_id[0], text)
                sent += 1
            except:
                failed += 1
            
            if sent % 100 == 0:
                bot.send_message(chat_id, f"📊 پیشرفت: {sent}/{total} ارسال شد")
        
        bot.send_message(
            chat_id,
            f"✅ **پیام همگانی با موفقیت ارسال شد!**\n\n"
            f"📊 آمار نهایی:\n"
            f"✅ موفق: {sent}\n"
            f"❌ ناموفق: {failed}\n"
            f"👥 مجموع: {total}"
        )
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطا در ارسال: {str(e)}")

# ==================== اجرا ====================
if __name__ == "__main__":
    print("🚀 سکوی ابری ساخت ربات با قابلیت مقیاس‌پذیری نامحدود راه‌اندازی شد...")
    print(f"📁 پوشه کاربران: {USERS_DIR}")
    print(f"📁 پوشه ربات‌ها: {BOTS_DIR}")
    print(f"📁 پوشه لاگ: {LOGS_DIR}")
    
    # پاک کردن tempهای منقضی شده
    if not REDIS_AVAILABLE:
        c.execute('''DELETE FROM temp WHERE expires < ?''', (int(time.time()),))
        conn.commit()
    
    bot.infinity_polling()
