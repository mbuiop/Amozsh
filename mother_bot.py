#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر - نسخه با قابلیت اجرای واقعی ربات کاربر
"""

import telebot
from telebot import types
import sqlite3
import os
import subprocess
import sys
import time
import hashlib
import json
import threading
import shutil
import re
import zipfile
import requests
import signal
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

# ==================== تنظیمات پایه ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
FILES_DIR = os.path.join(BASE_DIR, "user_files")
RUNNING_DIR = os.path.join(BASE_DIR, "running_bots")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(RUNNING_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# ==================== توکن ربات مادر ====================
BOT_TOKEN = "8541672444:AAF4PBn7-XqiXUgaK0arVajyZfcMWqbxSJ0"
bot = telebot.TeleBot(BOT_TOKEN)
bot.delete_webhook()

# ==================== لاگینگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            os.path.join(LOGS_DIR, 'mother_bot.log'),
            maxBytes=10485760,
            backupCount=5
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== دیتابیس SQLite ====================
DB_PATH = os.path.join(DB_DIR, 'mother_bot.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ایجاد جداول
with get_db() as conn:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance INTEGER DEFAULT 0,
            bots_count INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            last_active TIMESTAMP
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            token TEXT UNIQUE,
            name TEXT,
            username TEXT,
            file_path TEXT,
            pid INTEGER,
            status TEXT DEFAULT 'stopped',
            created_at TIMESTAMP,
            last_active TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()

# ==================== توابع کمکی ====================

def get_user(user_id):
    with get_db() as conn:
        user = conn.execute(
            'SELECT * FROM users WHERE user_id = ?',
            (user_id,)
        ).fetchone()
        return dict(user) if user else None

def create_user(user_id, username, first_name, last_name):
    with get_db() as conn:
        now = datetime.now().isoformat()
        conn.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, now, now))
        
        conn.execute('''
            UPDATE users SET last_active = ? WHERE user_id = ?
        ''', (now, user_id))
        conn.commit()

def add_bot(user_id, bot_id, token, name, username, file_path, pid=None):
    with get_db() as conn:
        now = datetime.now().isoformat()
        status = 'running' if pid else 'stopped'
        conn.execute('''
            INSERT INTO bots (id, user_id, token, name, username, file_path, pid, status, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (bot_id, user_id, token, name, username, file_path, pid, status, now, now))
        
        conn.execute('''
            UPDATE users SET bots_count = bots_count + 1, last_active = ?
            WHERE user_id = ?
        ''', (now, user_id))
        conn.commit()
        return True

def update_bot_status(bot_id, status, pid=None):
    with get_db() as conn:
        if pid:
            conn.execute('''
                UPDATE bots SET status = ?, pid = ?, last_active = ? WHERE id = ?
            ''', (status, pid, datetime.now().isoformat(), bot_id))
        else:
            conn.execute('''
                UPDATE bots SET status = ?, last_active = ? WHERE id = ?
            ''', (status, datetime.now().isoformat(), bot_id))
        conn.commit()

def get_user_bots(user_id):
    with get_db() as conn:
        bots = conn.execute('''
            SELECT * FROM bots WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,)).fetchall()
        return [dict(bot) for bot in bots]

def get_bot(bot_id):
    with get_db() as conn:
        bot = conn.execute('SELECT * FROM bots WHERE id = ?', (bot_id,)).fetchone()
        return dict(bot) if bot else None

def extract_token_from_code(code):
    patterns = [
        r'token\s*=\s*["\']([^"\']+)["\']',
        r'TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'API_TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'BOT_TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'bot\s*=\s*telebot\.TeleBot\(\s*["\']([^"\']+)["\']\s*\)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, code, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def validate_python_code(code):
    try:
        compile(code, '<string>', 'exec')
        return True, None
    except SyntaxError as e:
        return False, str(e)

def save_uploaded_file(user_id, file_data, file_name):
    user_dir = os.path.join(FILES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    timestamp = int(time.time())
    file_path = os.path.join(user_dir, f"{timestamp}_{file_name}")
    
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    return file_path

def extract_files_from_zip(zip_path, extract_to):
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    
    py_files = []
    for root, _, files in os.walk(extract_to):
        for file in files:
            if file.endswith('.py'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                py_files.append({
                    'name': file,
                    'path': file_path,
                    'content': content
                })
    
    return py_files

def run_bot_process(bot_id, token, code_content, user_id):
    """اجرای ربات کاربر به عنوان یک فرآیند جدا"""
    try:
        # ایجاد پوشه برای ربات در حال اجرا
        bot_run_dir = os.path.join(RUNNING_DIR, bot_id)
        os.makedirs(bot_run_dir, exist_ok=True)
        
        # ذخیره کد ربات
        bot_file = os.path.join(bot_run_dir, f"{bot_id}.py")
        with open(bot_file, 'w', encoding='utf-8') as f:
            f.write(code_content)
        
        # ذخیره توکن
        token_file = os.path.join(bot_run_dir, "token.txt")
        with open(token_file, 'w') as f:
            f.write(token)
        
        # ایجاد فایل لاگ
        log_file = os.path.join(bot_run_dir, "bot.log")
        
        # اجرای ربات به عنوان یک فرآیند جدا
        process = subprocess.Popen(
            [sys.executable, bot_file],
            stdout=open(log_file, 'a'),
            stderr=subprocess.STDOUT,
            cwd=bot_run_dir,
            start_new_session=True
        )
        
        logger.info(f"✅ ربات {bot_id} با PID {process.pid} اجرا شد")
        return process.pid
        
    except Exception as e:
        logger.error(f"خطا در اجرای ربات {bot_id}: {e}")
        return None

def stop_bot_process(pid):
    """توقف فرآیند ربات"""
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True
    except:
        return False

# ==================== مانیتورینگ ربات‌ها ====================
def monitor_running_bots():
    """بررسی ربات‌های در حال اجرا"""
    while True:
        try:
            with get_db() as conn:
                running_bots = conn.execute('SELECT id, pid FROM bots WHERE status = "running"').fetchall()
                
                for bot in running_bots:
                    bot_id, pid = bot
                    try:
                        # چک کردن اینکه پروسه هنوز زنده هست
                        os.kill(pid, 0)
                    except:
                        # پروسه مرده
                        conn.execute('UPDATE bots SET status = ? WHERE id = ?', ('stopped', bot_id))
                        conn.commit()
                        logger.info(f"⚠️ ربات {bot_id} متوقف شد")
            
            time.sleep(30)  # هر ۳۰ ثانیه چک کن
            
        except Exception as e:
            logger.error(f"خطا در مانیتورینگ: {e}")
            time.sleep(60)

# شروع مانیتورینگ در یک نخ جدا
monitor_thread = threading.Thread(target=monitor_running_bots, daemon=True)
monitor_thread.start()

# ==================== آمار ====================
start_time = datetime.now()
total_requests = 0
total_bots_created = 0

# ==================== هندلرهای ربات ====================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    global total_requests
    total_requests += 1
    
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    create_user(user_id, username, first_name, last_name)
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton('🤖 ساخت ربات جدید'),
        types.KeyboardButton('📋 ربات‌های من'),
        types.KeyboardButton('🔄 توقف ربات'),
        types.KeyboardButton('📊 آمار'),
        types.KeyboardButton('📚 راهنما')
    )
    
    bot.send_message(
        message.chat.id,
        f"🚀 **به ربات مادر خوش آمدید {first_name}!**\n\n"
        f"👤 کاربر: {user_id}\n"
        f"📤 فایل `.py` خود را آپلود کنید تا رباتتان ساخته و اجرا شود.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['help'])
def cmd_help(message):
    global total_requests
    total_requests += 1
    
    help_text = (
        "📚 **راهنمای استفاده**\n\n"
        "**🤖 ساخت و اجرای ربات:**\n"
        "1️⃣ فایل `.py` خود را آپلود کنید\n"
        "2️⃣ کد بررسی می‌شود\n"
        "3️⃣ توکن استخراج می‌شود\n"
        "4️⃣ ربات شما اجرا می‌شود\n\n"
        "**📁 آپلود فایل:**\n"
        "• فایل `.py` ساده\n"
        "• فایل `.zip` شامل چندین فایل\n"
        "• حداکثر حجم: ۵۰ مگابایت\n\n"
        "**🔑 توکن:**\n"
        "• توکن باید داخل کد باشه\n"
        "• مثال: TOKEN = '123456:ABCdef'\n\n"
        "**📋 مدیریت:**\n"
        "• /bots - لیست ربات‌های شما\n"
        "• /stop [bot_id] - توقف ربات\n"
        "• /stats - آمار کلی\n\n"
        "**📞 پشتیبانی:**\n"
        "@support_bot"
    )
    
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def cmd_stats(message):
    global total_requests, total_bots_created, start_time
    
    uptime = datetime.now() - start_time
    hours = uptime.total_seconds() / 3600
    
    with get_db() as conn:
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_bots = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
        running_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "running"').fetchone()[0]
    
    text = f"📊 **آمار ربات مادر**\n\n"
    text += f"⏱ آپتایم: {hours:.1f} ساعت\n"
    text += f"👥 کاربران: {total_users:,}\n"
    text += f"🤖 ربات‌های ساخته شده: {total_bots:,}\n"
    text += f"🟢 ربات‌های فعال: {running_bots:,}\n"
    text += f"📨 درخواست‌ها: {total_requests:,}\n"
    text += f"⚡ وضعیت: 🟢 فعال"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['bots'])
def cmd_bots(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 شما هنوز رباتی نساخته‌اید!"
        )
        return
    
    for b in bots[:5]:
        status_emoji = "🟢" if b['status'] == 'running' else "🔴"
        text = f"{status_emoji} **{b['name']}**\n"
        text += f"🔗 https://t.me/{b['username']}\n"
        text += f"🆔 `{b['id']}`\n"
        text += f"📊 وضعیت: {b['status']}\n"
        text += f"📅 {b['created_at'][:10]}\n"
        
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def cmd_stop(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ لطفاً آیدی ربات را وارد کنید:\n/stop bot_id")
        return
    
    bot_id = parts[1]
    user_id = message.from_user.id
    
    bot_info = get_bot(bot_id)
    
    if not bot_info or bot_info['user_id'] != user_id:
        bot.reply_to(message, "❌ ربات پیدا نشد یا مالک آن نیستید!")
        return
    
    if bot_info['status'] != 'running':
        bot.reply_to(message, "❌ این ربات در حال اجرا نیست!")
        return
    
    if stop_bot_process(bot_info['pid']):
        update_bot_status(bot_id, 'stopped')
        bot.reply_to(message, f"✅ ربات {bot_info['name']} متوقف شد.")
    else:
        bot.reply_to(message, "❌ خطا در توقف ربات!")

@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot(message):
    bot.send_message(
        message.chat.id,
        "📤 **آپلود فایل**\n\n"
        "فایل `.py` یا `.zip` خود را ارسال کنید:\n\n"
        "✅ توکن باید داخل کد باشه\n"
        "✅ حجم فایل حداکثر ۵۰ مگابایت\n"
        "✅ پس از آپلود، ربات شما اجرا می‌شود"
    )

@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    cmd_bots(message)

@bot.message_handler(func=lambda m: m.text == '🔄 توقف ربات')
def stop_prompt(message):
    bot.send_message(
        message.chat.id,
        "برای توقف ربات از دستور زیر استفاده کنید:\n"
        "/stop [bot_id]\n\n"
        "مثال: /stop abc123"
    )

@bot.message_handler(func=lambda m: m.text == '📊 آمار')
def stats(message):
    cmd_stats(message)

@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def help(message):
    cmd_help(message)

@bot.message_handler(content_types=['document'])
def handle_file(message):
    global total_requests, total_bots_created
    total_requests += 1
    
    user_id = message.from_user.id
    file_name = message.document.file_name
    user = get_user(user_id)
    
    if not user:
        create_user(user_id, message.from_user.username or "", 
                   message.from_user.first_name or "", 
                   message.from_user.last_name or "")
    
    if not (file_name.endswith('.py') or file_name.endswith('.zip')):
        bot.reply_to(message, "❌ فقط فایل‌های `.py` یا `.zip` مجاز هستند!")
        return
    
    if message.document.file_size > 50 * 1024 * 1024:
        bot.reply_to(message, "❌ حجم فایل نباید بیشتر از ۵۰ مگابایت باشد!")
        return
    
    status_msg = bot.reply_to(message, "🔄 در حال پردازش فایل...")
    
    try:
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره فایل
        file_path = save_uploaded_file(user_id, downloaded_file, file_name)
        
        files_content = {}
        main_code = ""
        
        if file_name.endswith('.zip'):
            # استخراج فایل‌های zip
            extract_dir = os.path.join(FILES_DIR, str(user_id), f"extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            
            py_files = extract_files_from_zip(file_path, extract_dir)
            for pf in py_files:
                files_content[pf['name']] = pf['content']
                if pf['name'] == 'bot.py' or pf['name'] == 'main.py' or len(pf['name']) == len(main_file):
                    main_code = pf['content']
            
            shutil.rmtree(extract_dir)
            
            if not main_code and py_files:
                main_code = py_files[0]['content']
        
        else:  # فایل .py
            with open(file_path, 'r', encoding='utf-8') as f:
                main_code = f.read()
            files_content[file_name] = main_code
        
        if not main_code:
            bot.edit_message_text(
                "❌ هیچ فایل پایتونی پیدا نشد!",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # اعتبارسنجی کد
        is_valid, error = validate_python_code(main_code)
        if not is_valid:
            bot.edit_message_text(
                f"❌ خطای نحوی در کد:\n```\n{error}\n```",
                message.chat.id,
                status_msg.message_id,
                parse_mode="Markdown"
            )
            return
        
        # استخراج توکن
        token = extract_token_from_code(main_code)
        if not token:
            bot.edit_message_text(
                "❌ توکن در کد پیدا نشد!\n"
                "مثال: TOKEN = '123456:ABCdef'",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # تست توکن
        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if response.status_code != 200:
                bot.edit_message_text(
                    "❌ توکن معتبر نیست!",
                    message.chat.id,
                    status_msg.message_id
                )
                return
            
            bot_info = response.json()['result']
            bot_name = bot_info['first_name']
            bot_username = bot_info['username']
            
        except Exception as e:
            bot.edit_message_text(
                f"❌ خطا در بررسی توکن: {str(e)}",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # آیدی یکتا برای ربات
        bot_id = hashlib.md5(f"{user_id}_{token}_{time.time()}".encode()).hexdigest()[:10]
        
        bot.edit_message_text(
            f"✅ کد معتبر است. در حال اجرای ربات...",
            message.chat.id,
            status_msg.message_id
        )
        
        # اجرای ربات
        pid = run_bot_process(bot_id, token, main_code, user_id)
        
        if pid:
            # ذخیره در دیتابیس
            add_bot(user_id, bot_id, token, bot_name, bot_username, file_path, pid)
            total_bots_created += 1
            
            bot.edit_message_text(
                f"✅ **ربات با موفقیت ساخته و اجرا شد!** 🎉\n\n"
                f"🤖 نام: {bot_name}\n"
                f"🔗 لینک: https://t.me/{bot_username}\n"
                f"🆔 آیدی ربات: {bot_id}\n"
                f"🔄 PID: {pid}\n"
                f"📦 فایل‌ها: {len(files_content)}\n"
                f"🔄 وضعیت: در حال اجرا\n\n"
                f"💡 از /bots برای مشاهده لیست ربات‌ها استفاده کن.\n"
                f"💡 برای توقف: /stop {bot_id}",
                message.chat.id,
                status_msg.message_id,
                parse_mode="Markdown"
            )
        else:
            bot.edit_message_text(
                "❌ خطا در اجرای ربات!",
                message.chat.id,
                status_msg.message_id
            )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(
            f"❌ خطا: {str(e)}",
            message.chat.id,
            status_msg.message_id
        )

# ==================== اجرا ====================
if __name__ == "__main__":
    logger.info("🚀 ربات مادر با قابلیت اجرای ربات‌ها راه‌اندازی شد...")
    logger.info(f"📁 پوشه فایل‌ها: {FILES_DIR}")
    logger.info(f"📁 پوشه ربات‌های در حال اجرا: {RUNNING_DIR}")
    logger.info(f"📁 پوشه دیتابیس: {DB_DIR}")
    
    try:
        bot.infinity_polling(timeout=60)
    except Exception as e:
        logger.error(f"خطا: {e}")
        time.sleep(5)
        bot.infinity_polling(timeout=60)
