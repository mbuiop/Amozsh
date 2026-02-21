#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر نهایی - با موتور اجرای پیشرفته و نصب کتابخانه
نسخه 8.0 - فوق العاده قدرتمند و بدون خطا
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
import psutil
import secrets
import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ==================== تنظیمات پایه ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
FILES_DIR = os.path.join(BASE_DIR, "user_files")
RUNNING_DIR = os.path.join(BASE_DIR, "running_bots")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RECEIPTS_DIR = os.path.join(BASE_DIR, "receipts")

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(RUNNING_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

# ==================== توکن ربات مادر ====================
BOT_TOKEN = "8541672444:AAF4PBn7-XqiXUgaK0arVajyZfcMWqbxSJ0"
bot = telebot.TeleBot(BOT_TOKEN)
bot.delete_webhook()

# ==================== آیدی ادمین ====================
ADMIN_IDS = [327855654]

# ==================== اطلاعات کارت (مخفی) ====================
CARD_NUMBER = "5892101187322777"
CARD_HOLDER = "مرتضی نیکخو خنجری"
PRICE = 2000000

# ==================== لاگینگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            os.path.join(LOGS_DIR, 'mother_bot.log'),
            maxBytes=10485760,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== دیتابیس SQLite ====================
DB_PATH = os.path.join(DB_DIR, 'mother_bot.db')

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

# ایجاد جداول
with get_db() as conn:
    # جدول کاربران
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            balance INTEGER DEFAULT 0,
            bots_count INTEGER DEFAULT 0,
            max_bots INTEGER DEFAULT 1,
            referral_code TEXT UNIQUE,
            referred_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            verified_referrals INTEGER DEFAULT 0,
            payment_status TEXT DEFAULT 'pending',
            payment_date TIMESTAMP,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP,
            last_active TIMESTAMP
        )
    ''')
    
    # جدول ربات‌ها
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            token TEXT,
            name TEXT,
            username TEXT,
            file_path TEXT,
            folder_path TEXT,
            pid INTEGER,
            status TEXT DEFAULT 'stopped',
            created_at TIMESTAMP,
            last_active TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
        )
    ''')
    
    # جدول فیش‌های واریزی
    conn.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount INTEGER,
            receipt_path TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP,
            reviewed_at TIMESTAMP,
            reviewed_by INTEGER,
            payment_code TEXT UNIQUE,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()

# ==================== توابع کمکی ====================

def generate_referral_code(user_id):
    """تولید کد رفرال یکتا"""
    return hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:8]

def get_user(user_id):
    """گرفتن اطلاعات کاربر"""
    try:
        with get_db() as conn:
            user = conn.execute(
                'SELECT * FROM users WHERE user_id = ?',
                (user_id,)
            ).fetchone()
            return dict(user) if user else None
    except:
        return None

def create_user(user_id, username, first_name, last_name, referred_by=None):
    """ایجاد کاربر جدید"""
    try:
        with get_db() as conn:
            now = datetime.now().isoformat()
            referral_code = generate_referral_code(user_id)
            
            conn.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, last_name, referral_code, referred_by, created_at, last_active, payment_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, referral_code, referred_by, now, now, 'pending'))
            
            conn.execute('''
                UPDATE users SET last_active = ? WHERE user_id = ?
            ''', (now, user_id))
            conn.commit()
            
            if referred_by:
                conn.execute('''
                    UPDATE users SET referrals_count = referrals_count + 1
                    WHERE user_id = ?
                ''', (referred_by,))
                conn.commit()
            return True
    except Exception as e:
        logger.error(f"خطا در create_user: {e}")
        return False

def check_payment(user_id):
    """بررسی وضعیت پرداخت کاربر"""
    try:
        with get_db() as conn:
            user = conn.execute('SELECT payment_status FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user and user['payment_status'] == 'approved':
                return True
            
            receipt = conn.execute('''
                SELECT id FROM receipts 
                WHERE user_id = ? AND status = 'approved'
                ORDER BY created_at DESC LIMIT 1
            ''', (user_id,)).fetchone()
            
            if receipt:
                conn.execute('UPDATE users SET payment_status = ? WHERE user_id = ?', 
                            ('approved', user_id))
                conn.commit()
                return True
            return False
    except:
        return False

def check_bot_limit(user_id):
    """بررسی محدودیت تعداد ربات"""
    try:
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if not user:
                return True, 1, 0
            
            extra_bots = user['verified_referrals'] // 5
            max_bots = 1 + extra_bots
            current_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE user_id = ?', (user_id,)).fetchone()[0]
            
            return current_bots < max_bots, max_bots, current_bots
    except:
        return True, 1, 0

def get_user_bots(user_id):
    """دریافت لیست ربات‌های کاربر"""
    try:
        with get_db() as conn:
            bots = conn.execute('''
                SELECT * FROM bots WHERE user_id = ? ORDER BY created_at DESC
            ''', (user_id,)).fetchall()
            return [dict(bot) for bot in bots]
    except:
        return []

def get_bot(bot_id):
    """دریافت اطلاعات یک ربات"""
    try:
        with get_db() as conn:
            bot = conn.execute('SELECT * FROM bots WHERE id = ?', (bot_id,)).fetchone()
            return dict(bot) if bot else None
    except:
        return None

def update_bot_status(bot_id, status, pid=None):
    """به‌روزرسانی وضعیت ربات"""
    try:
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
            return True
    except:
        return False

def delete_bot(bot_id, user_id):
    """حذف کامل ربات"""
    try:
        with get_db() as conn:
            bot = conn.execute('SELECT * FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id)).fetchone()
            if not bot:
                return False
            
            if bot['pid']:
                try:
                    os.kill(bot['pid'], signal.SIGTERM)
                except:
                    pass
            
            if bot['file_path'] and os.path.exists(bot['file_path']):
                os.remove(bot['file_path'])
            
            if bot['folder_path'] and os.path.exists(bot['folder_path']):
                shutil.rmtree(bot['folder_path'])
            
            conn.execute('DELETE FROM bots WHERE id = ?', (bot_id,))
            conn.execute('UPDATE users SET bots_count = bots_count - 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            return True
    except:
        return False

def save_uploaded_file(user_id, file_data, file_name):
    """ذخیره فایل آپلود شده"""
    try:
        user_dir = os.path.join(FILES_DIR, str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        timestamp = int(time.time())
        file_path = os.path.join(user_dir, f"{timestamp}_{file_name}")
        
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        return file_path
    except:
        return None

def extract_files_from_zip(zip_path, extract_to):
    """استخراج فایل‌های zip"""
    py_files = []
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
        
        for root, _, files in os.walk(extract_to):
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        py_files.append({
                            'name': file,
                            'path': file_path,
                            'content': content
                        })
                    except:
                        pass
    except:
        pass
    return py_files

def extract_token_from_code(code):
    """استخراج توکن از کد"""
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

def add_bot(user_id, bot_id, token, name, username, file_path, folder_path=None, pid=None):
    """افزودن ربات به دیتابیس"""
    try:
        with get_db() as conn:
            now = datetime.now().isoformat()
            status = 'running' if pid else 'stopped'
            
            conn.execute('''
                INSERT INTO bots 
                (id, user_id, token, name, username, file_path, folder_path, pid, status, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bot_id, user_id, token, name, username, file_path, folder_path, pid, status, now, now))
            
            conn.execute('''
                UPDATE users SET bots_count = bots_count + 1, last_active = ?
                WHERE user_id = ?
            ''', (now, user_id))
            conn.commit()
            
            user = conn.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user and user['referred_by']:
                conn.execute('''
                    UPDATE users SET verified_referrals = verified_referrals + 1
                    WHERE user_id = ?
                ''', (user['referred_by'],))
                conn.commit()
            
            return True
    except:
        return False

# ==================== موتور اجرای پیشرفته ====================
class AdvancedBotEngine:
    """موتور اجرای پیشرفته ربات‌ها"""
    
    def __init__(self):
        self.running_processes = {}
        self.lock = threading.Lock()
    
    def install_library(self, lib_name):
        """نصب کتابخانه"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", lib_name],
                capture_output=True,
                text=True,
                timeout=60
            )
            return result.returncode == 0, result.stdout
        except:
            return False, "خطا در نصب"
    
    def detect_requirements(self, code):
        """تشخیص کتابخانه‌های مورد نیاز"""
        imports = set()
        lines = code.split('\n')
        
        for line in lines:
            line = line.strip()
            if line.startswith('import '):
                parts = line.split()
                if len(parts) > 1:
                    lib = parts[1].split('.')[0]
                    if lib not in ['os', 'sys', 'time', 'datetime', 'json', 're', 'math']:
                        imports.add(lib)
            elif line.startswith('from '):
                parts = line.split()
                if len(parts) > 1:
                    lib = parts[1].split('.')[0]
                    if lib not in ['os', 'sys', 'time', 'datetime', 'json', 're', 'math']:
                        imports.add(lib)
        
        return list(imports)
    
    def prepare_code(self, code):
        """آماده‌سازی کد برای اجرا"""
        if 'def main' not in code and 'if __name__ == "__main__"' not in code:
            if 'bot.infinity_polling' in code:
                code += '\n\nif __name__ == "__main__":\n    print("✅ ربات در حال اجراست...")\n    bot.infinity_polling()\n'
        return code
    
    def run_bot(self, bot_id, user_id, code, token):
        """اجرای ربات"""
        result = {
            'success': False,
            'pid': None,
            'error': None,
            'installed': []
        }
        
        try:
            # تشخیص و نصب کتابخانه‌ها
            requirements = self.detect_requirements(code)
            installed = []
            
            for lib in requirements:
                try:
                    __import__(lib)
                except:
                    success, _ = self.install_library(lib)
                    if success:
                        installed.append(lib)
            
            result['installed'] = installed
            
            # آماده‌سازی کد
            code = self.prepare_code(code)
            
            # ایجاد پوشه موقت
            bot_dir = os.path.join(RUNNING_DIR, bot_id)
            os.makedirs(bot_dir, exist_ok=True)
            
            # ذخیره کد
            code_path = os.path.join(bot_dir, 'bot.py')
            with open(code_path, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # ذخیره توکن
            with open(os.path.join(bot_dir, 'token.txt'), 'w') as f:
                f.write(token)
            
            # فایل لاگ
            log_file = os.path.join(bot_dir, 'bot.log')
            
            # اجرا
            process = subprocess.Popen(
                [sys.executable, code_path],
                stdout=open(log_file, 'a'),
                stderr=subprocess.STDOUT,
                cwd=bot_dir,
                start_new_session=True
            )
            
            # ذخیره اطلاعات
            with self.lock:
                self.running_processes[bot_id] = {
                    'process': process,
                    'dir': bot_dir,
                    'pid': process.pid,
                    'start_time': time.time()
                }
            
            # صبر برای بررسی خطا
            time.sleep(2)
            
            if process.poll() is None:
                result['success'] = True
                result['pid'] = process.pid
            else:
                if os.path.exists(log_file):
                    with open(log_file, 'r') as f:
                        result['error'] = f.read()[-500:]
                else:
                    result['error'] = "خطای ناشناخته"
                    
        except Exception as e:
            result['error'] = str(e)
        
        return result
    
    def stop_bot(self, bot_id):
        """توقف ربات"""
        with self.lock:
            if bot_id in self.running_processes:
                try:
                    pid = self.running_processes[bot_id]['pid']
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    time.sleep(1)
                    
                    if bot_id in self.running_processes:
                        del self.running_processes[bot_id]
                    return True
                except:
                    pass
        return False
    
    def get_status(self, bot_id):
        """وضعیت ربات"""
        with self.lock:
            if bot_id in self.running_processes:
                process = self.running_processes[bot_id]['process']
                if process.poll() is None:
                    try:
                        p = psutil.Process(process.pid)
                        return {
                            'running': True,
                            'pid': process.pid,
                            'cpu': p.cpu_percent(),
                            'memory': p.memory_percent()
                        }
                    except:
                        return {'running': True, 'pid': process.pid}
        return {'running': False}

# نمونه موتور
bot_engine = AdvancedBotEngine()

# ==================== کتابخانه منیجر ====================
class LibraryManager:
    """مدیریت نصب کتابخانه‌ها"""
    
    def __init__(self):
        self.common_libs = {
            'requests': 'requests',
            'numpy': 'numpy',
            'pandas': 'pandas',
            'flask': 'flask',
            'django': 'django',
            'pillow': 'Pillow',
            'beautifulsoup4': 'beautifulsoup4',
            'selenium': 'selenium',
            'scrapy': 'Scrapy',
            'matplotlib': 'matplotlib',
            'pyTelegramBotAPI': 'pyTelegramBotAPI',
            'aiogram': 'aiogram',
            'aiohttp': 'aiohttp',
            'fastapi': 'fastapi',
            'jdatetime': 'jdatetime',
            'pytz': 'pytz',
            'qrcode': 'qrcode[pil]',
            'yt-dlp': 'yt-dlp',
            'cryptography': 'cryptography',
            'loguru': 'loguru'
        }
    
    def install(self, lib_name, chat_id, message_id=None):
        """نصب کتابخانه"""
        try:
            msg = bot.send_message(chat_id, f"🔄 در حال نصب {lib_name}...")
            
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", lib_name],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                bot.edit_message_text(
                    f"✅ کتابخانه {lib_name} با موفقیت نصب شد.",
                    chat_id,
                    msg.message_id
                )
                return True
            else:
                bot.edit_message_text(
                    f"❌ خطا در نصب {lib_name}:\n{result.stderr[:200]}",
                    chat_id,
                    msg.message_id
                )
                return False
                
        except subprocess.TimeoutExpired:
            bot.send_message(chat_id, f"❌ زمان نصب {lib_name} بیش از حد طول کشید.")
            return False
        except Exception as e:
            bot.send_message(chat_id, f"❌ خطا: {str(e)}")
            return False

library_manager = LibraryManager()

# ==================== منوی اصلی ====================
def get_main_menu(is_admin=False):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    buttons = [
        types.KeyboardButton('🤖 ساخت ربات جدید'),
        types.KeyboardButton('📋 ربات‌های من'),
        types.KeyboardButton('🔄 فعال/غیرفعال کردن'),
        types.KeyboardButton('🗑 حذف ربات'),
        types.KeyboardButton('💰 کیف پول و رفرال'),
        types.KeyboardButton('📚 راهنما'),
        types.KeyboardButton('📦 نصب کتابخانه'),
        types.KeyboardButton('📊 آمار'),
        types.KeyboardButton('📞 پشتیبانی')
    ]
    
    if is_admin:
        buttons.append(types.KeyboardButton('👑 پنل ادمین'))
    
    markup.add(*buttons)
    return markup

# ==================== هندلر استارت ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    referred_by = None
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        try:
            with get_db() as conn:
                referrer = conn.execute('SELECT user_id FROM users WHERE referral_code = ?', (ref_code,)).fetchone()
                if referrer:
                    referred_by = referrer['user_id']
                    
                    try:
                        bot.send_message(
                            referred_by,
                            f"🎉 یک نفر با لینک رفرال شما وارد شد!\n\n👤 {first_name}\n🆔 {user_id}"
                        )
                    except:
                        pass
        except:
            pass
    
    create_user(user_id, username, first_name, last_name, referred_by)
    
    user = get_user(user_id) or {'referral_code': '', 'referrals_count': 0, 'verified_referrals': 0}
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    is_admin = user_id in ADMIN_IDS
    markup = get_main_menu(is_admin)
    
    welcome_text = (
        f"🚀 به ربات مادر نهایی خوش آمدید {first_name}!\n\n"
        f"👤 آیدی شما: {user_id}\n"
        f"🎁 کد رفرال شما: {user['referral_code']}\n"
        f"🔗 لینک دعوت: {referral_link}\n\n"
        f"📊 آمار رفرال:\n"
        f"• کلیک‌ها: {user['referrals_count']}\n"
        f"• ساخته شده: {user['verified_referrals']}\n\n"
        f"💡 هر ۵ نفر = ۱ ربات اضافه\n"
        f"📤 فایل .py خود را آپلود کنید"
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=markup
    )

# ==================== کیف پول و رفرال ====================
@bot.message_handler(func=lambda m: m.text == '💰 کیف پول و رفرال')
def wallet_ref(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.send_message(message.chat.id, "❌ لطفاً /start را بزنید")
        return
    
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    payment_approved = check_payment(user_id)
    can_create, max_bots, current_bots = check_bot_limit(user_id)
    
    text = f"💰 کیف پول و سیستم رفرال\n\n"
    text += f"👤 کاربر: {user['first_name']}\n"
    text += f"🆔 آیدی: {user_id}\n\n"
    text += f"💳 وضعیت پرداخت:\n"
    text += f"{'✅ تایید شده' if payment_approved else '⏳ در انتظار تایید'}\n\n"
    text += f"🎁 کد رفرال شما:\n{user['referral_code']}\n"
    text += f"🔗 لینک دعوت:\n{referral_link}\n\n"
    text += f"📊 آمار رفرال:\n"
    text += f"• کلیک‌ها: {user['referrals_count']}\n"
    text += f"• ساخته شده: {user['verified_referrals']}\n\n"
    text += f"🤖 ربات‌ها:\n"
    text += f"• فعلی: {current_bots}\n"
    text += f"• حداکثر: {max_bots}\n\n"
    
    if not payment_approved:
        text += f"💳 برای ساخت ربات:\n"
        text += f"مبلغ: {PRICE:,} تومان\n"
        text += f"شماره کارت: {CARD_NUMBER}\n\n"
        text += f"📸 پس از واریز، تصویر فیش را ارسال کنید"
    
    bot.send_message(message.chat.id, text)

# ==================== فیش واریزی ====================
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    try:
        with get_db() as conn:
            existing = conn.execute('''
                SELECT id FROM receipts 
                WHERE user_id = ? AND status = 'pending'
            ''', (user_id,)).fetchone()
            
            if existing:
                bot.reply_to(message, "⏳ شما یک فیش در انتظار بررسی دارید")
                return
    except:
        pass
    
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        payment_code = hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:8].upper()
        receipt_path = os.path.join(RECEIPTS_DIR, f"{user_id}_{payment_code}.jpg")
        
        with open(receipt_path, 'wb') as f:
            f.write(downloaded_file)
        
        with get_db() as conn:
            conn.execute('''
                INSERT INTO receipts (user_id, amount, receipt_path, created_at, payment_code)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, PRICE, receipt_path, datetime.now().isoformat(), payment_code))
            conn.commit()
        
        bot.reply_to(
            message,
            f"✅ فیش دریافت شد\n"
            f"💰 مبلغ: {PRICE:,} تومان\n"
            f"🆔 کد پیگیری: {payment_code}\n\n"
            f"پس از بررسی توسط ادمین فعال می‌شود"
        )
        
        for admin_id in ADMIN_IDS:
            try:
                bot.send_message(
                    admin_id,
                    f"📸 فیش جدید\n👤 {user_id}\n💰 {PRICE:,} تومان\n🆔 {payment_code}"
                )
            except:
                pass
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

# ==================== نصب کتابخانه ====================
@bot.message_handler(func=lambda m: m.text == '📦 نصب کتابخانه')
def install_library_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    libs = [
        ('requests', 'requests'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('flask', 'flask'),
        ('django', 'django'),
        ('pillow', 'Pillow'),
        ('beautifulsoup4', 'beautifulsoup4'),
        ('selenium', 'selenium'),
        ('pyTelegramBotAPI', 'pyTelegramBotAPI'),
        ('aiogram', 'aiogram'),
        ('jdatetime', 'jdatetime'),
        ('🔧 دستی', 'custom')
    ]
    
    for name, data in libs:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"lib_{data}"))
    
    bot.send_message(
        message.chat.id,
        "📦 کتابخانه مورد نظر را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('lib_'))
def install_library_callback(call):
    lib = call.data.replace('lib_', '')
    
    if lib == 'custom':
        msg = bot.send_message(
            call.message.chat.id,
            "📦 نام کتابخانه را وارد کنید:"
        )
        bot.register_next_step_handler(msg, install_custom_library)
        return
    
    bot.answer_callback_query(call.id, f"در حال نصب {lib}...")
    library_manager.install(lib, call.message.chat.id)

def install_custom_library(message):
    lib = message.text.strip()
    library_manager.install(lib, message.chat.id)

# ==================== ساخت ربات جدید ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot(message):
    user_id = message.from_user.id
    
    if not check_payment(user_id):
        bot.send_message(
            message.chat.id,
            f"❌ ابتدا هزینه را پرداخت کنید\n"
            f"💰 مبلغ: {PRICE:,} تومان\n"
            f"💳 کارت: {CARD_NUMBER}"
        )
        return
    
    can_create, max_bots, current_bots = check_bot_limit(user_id)
    
    if not can_create:
        bot.send_message(
            message.chat.id,
            f"❌ شما به حداکثر تعداد ربات ({max_bots}) رسیده‌اید!\n"
            f"برای ساخت ربات جدید:\n"
            f"1️⃣ یکی از ربات‌ها را حذف کنید\n"
            f"2️⃣ یا با دعوت دوستان ربات اضافه بگیرید"
        )
        return
    
    bot.send_message(
        message.chat.id,
        "📤 فایل `.py` یا `.zip` خود را ارسال کنید\n"
        "✅ حجم حداکثر ۵۰ مگابایت\n"
        "✅ توکن داخل کد باشد"
    )

# ==================== آپلود فایل ====================
@bot.message_handler(content_types=['document'])
def handle_build_file(message):
    user_id = message.from_user.id
    
    if not check_payment(user_id):
        bot.reply_to(message, "❌ ابتدا هزینه را پرداخت کنید")
        return
    
    file_name = message.document.file_name
    
    if not (file_name.endswith('.py') or file_name.endswith('.zip')):
        bot.reply_to(message, "❌ فقط فایل‌های `.py` یا `.zip` مجاز هستند!")
        return
    
    if message.document.file_size > 50 * 1024 * 1024:
        bot.reply_to(message, "❌ حجم فایل نباید بیشتر از ۵۰ مگابایت باشد!")
        return
    
    status_msg = bot.reply_to(message, "🔄 در حال پردازش فایل...")
    
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        file_path = save_uploaded_file(user_id, downloaded_file, file_name)
        if not file_path:
            bot.edit_message_text("❌ خطا در ذخیره فایل", message.chat.id, status_msg.message_id)
            return
        
        main_code = ""
        
        if file_name.endswith('.zip'):
            extract_dir = os.path.join(FILES_DIR, str(user_id), f"extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            
            py_files = extract_files_from_zip(file_path, extract_dir)
            for pf in py_files:
                if pf['name'] in ['bot.py', 'main.py', 'run.py']:
                    main_code = pf['content']
                    break
            
            if not main_code and py_files:
                main_code = py_files[0]['content']
            
            shutil.rmtree(extract_dir, ignore_errors=True)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    main_code = f.read()
            except:
                with open(file_path, 'r', encoding='cp1256') as f:
                    main_code = f.read()
        
        if not main_code:
            bot.edit_message_text("❌ هیچ فایل پایتونی پیدا نشد!", message.chat.id, status_msg.message_id)
            return
        
        token = extract_token_from_code(main_code)
        if not token:
            bot.edit_message_text("❌ توکن در کد پیدا نشد!", message.chat.id, status_msg.message_id)
            return
        
        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if response.status_code != 200:
                bot.edit_message_text("❌ توکن معتبر نیست!", message.chat.id, status_msg.message_id)
                return
            
            bot_info = response.json()['result']
            bot_name = bot_info['first_name']
            bot_username = bot_info['username']
        except Exception as e:
            bot.edit_message_text(f"❌ خطا در بررسی توکن: {str(e)}", message.chat.id, status_msg.message_id)
            return
        
        bot.edit_message_text("⚡ در حال اجرا با موتور پیشرفته...", message.chat.id, status_msg.message_id)
        
        # اجرا با موتور پیشرفته
        result = bot_engine.run_bot(
            hashlib.md5(f"{user_id}{token}{time.time()}".encode()).hexdigest()[:12],
            user_id,
            main_code,
            token
        )
        
        if result['success']:
            bot_id = hashlib.md5(f"{user_id}{token}{time.time()}".encode()).hexdigest()[:10]
            add_bot(user_id, bot_id, token, bot_name, bot_username, file_path, None, result['pid'])
            
            reply = f"✅ ربات با موفقیت ساخته شد! 🎉\n\n"
            reply += f"🤖 نام: {bot_name}\n"
            reply += f"🔗 لینک: https://t.me/{bot_username}\n"
            reply += f"🆔 آیدی: {bot_id}\n"
            reply += f"🔄 PID: {result['pid']}\n"
            
            if result.get('installed'):
                reply += f"📦 کتابخانه‌های نصب شده: {', '.join(result['installed'])}\n"
            
            bot.edit_message_text(reply, message.chat.id, status_msg.message_id)
        else:
            error = result.get('error', 'خطای ناشناخته')
            bot.edit_message_text(f"❌ خطا در اجرا:\n{error}", message.chat.id, status_msg.message_id)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        bot.edit_message_text(f"❌ خطا: {str(e)}", message.chat.id, status_msg.message_id)

# ==================== ربات‌های من ====================
@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(message.chat.id, "📋 شما رباتی ندارید!")
        return
    
    for b in bots[:10]:
        status_info = bot_engine.get_status(b['id']) if b['pid'] else {'running': False}
        
        status_emoji = "🟢" if status_info['running'] else "🔴"
        status_text = "در حال اجرا" if status_info['running'] else "متوقف"
        
        text = f"{status_emoji} **{b['name']}**\n"
        text += f"🔗 https://t.me/{b['username']}\n"
        text += f"🆔 `{b['id']}`\n"
        text += f"📊 وضعیت: {status_text}\n"
        
        if status_info.get('running'):
            text += f"💻 CPU: {status_info.get('cpu', 0):.1f}%\n"
            text += f"🧠 RAM: {status_info.get('memory', 0):.1f}%\n"
        
        text += f"📅 {b['created_at'][:10]}\n"
        
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ==================== فعال/غیرفعال کردن ====================
@bot.message_handler(func=lambda m: m.text == '🔄 فعال/غیرفعال کردن')
def toggle_prompt(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(message.chat.id, "📋 شما رباتی ندارید!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in bots:
        status = "🟢" if b['status'] == 'running' else "🔴"
        btn = types.InlineKeyboardButton(
            f"{status} {b['name']}",
            callback_data=f"toggle_{b['id']}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "🔄 ربات مورد نظر را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_'))
def toggle_bot(call):
    bot_id = call.data.replace('toggle_', '')
    user_id = call.from_user.id
    bot_info = get_bot(bot_id)
    
    if not bot_info or bot_info['user_id'] != user_id:
        bot.answer_callback_query(call.id, "❌ ربات پیدا نشد!")
        return
    
    if bot_info['status'] == 'running':
        if bot_engine.stop_bot(bot_id):
            update_bot_status(bot_id, 'stopped')
            bot.answer_callback_query(call.id, "✅ ربات متوقف شد")
            bot.edit_message_text(
                f"✅ ربات {bot_info['name']} متوقف شد.",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.answer_callback_query(call.id, "❌ خطا در توقف!")
    else:
        bot.answer_callback_query(call.id, "❌ ربات فعال نیست")

# ==================== حذف ربات ====================
@bot.message_handler(func=lambda m: m.text == '🗑 حذف ربات')
def delete_prompt(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(message.chat.id, "📋 شما رباتی ندارید!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for b in bots:
        btn = types.InlineKeyboardButton(
            f"🗑 {b['name']}",
            callback_data=f"delete_{b['id']}"
        )
        markup.add(btn)
    
    bot.send_message(
        message.chat.id,
        "⚠️ ربات مورد نظر را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def confirm_delete(call):
    bot_id = call.data.replace('delete_', '')
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("✅ بله", callback_data=f"confirm_del_{bot_id}")
    btn2 = types.InlineKeyboardButton("❌ خیر", callback_data="cancel_del")
    markup.add(btn1, btn2)
    
    bot.edit_message_text(
        "⚠️ آیا از حذف این ربات اطمینان دارید؟",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_del_'))
def do_delete(call):
    bot_id = call.data.replace('confirm_del_', '')
    user_id = call.from_user.id
    
    bot_engine.stop_bot(bot_id)
    
    if delete_bot(bot_id, user_id):
        bot.edit_message_text(
            "✅ ربات با موفقیت حذف شد.",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.edit_message_text(
            "❌ خطا در حذف ربات!",
            call.message.chat.id,
            call.message.message_id
        )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_del')
def cancel_delete(call):
    bot.edit_message_text(
        "❌ عملیات حذف لغو شد.",
        call.message.chat.id,
        call.message.message_id
    )

# ==================== راهنما ====================
@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def guide(message):
    user = get_user(message.from_user.id) or {'referral_code': ''}
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    text = (
        "📚 راهنمای کامل\n\n"
        "1️⃣ ساخت ربات:\n"
        f"   • کارت: {CARD_NUMBER}\n"
        "   • فایل .py آپلود کن\n"
        "   • توکن داخل کد باشه\n\n"
        "2️⃣ رفرال:\n"
        f"   • لینک شما: {referral_link}\n"
        "   • هر ۵ نفر = ۱ ربات اضافه\n\n"
        "3️⃣ کتابخانه:\n"
        "   • از منوی نصب کتابخانه استفاده کن\n"
        "   • کتابخانه‌ها خودکار نصب می‌شوند\n\n"
        "4️⃣ پشتیبانی:\n"
        "   • @shahraghee13"
    )
    
    bot.send_message(message.chat.id, text)

# ==================== آمار ====================
@bot.message_handler(func=lambda m: m.text == '📊 آمار')
def stats(message):
    try:
        with get_db() as conn:
            total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            total_bots = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
            running_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "running"').fetchone()[0]
            total_payments = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "approved"').fetchone()[0]
        
        text = f"📊 آمار\n"
        text += f"👥 کاربران: {total_users}\n"
        text += f"🤖 کل ربات‌ها: {total_bots}\n"
        text += f"🟢 فعال: {running_bots}\n"
        text += f"💰 پرداخت‌ها: {total_payments}"
        
        bot.send_message(message.chat.id, text)
    except:
        bot.send_message(message.chat.id, "📊 آمار در دسترس نیست")

# ==================== پشتیبانی ====================
@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(
        message.chat.id,
        "📞 پشتیبانی: @shahraghee13"
    )

# ==================== پنل ادمین ====================
@bot.message_handler(func=lambda m: m.text == '👑 پنل ادمین')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ شما دسترسی ادمین ندارید!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📸 فیش‌ها", callback_data="admin_receipts"),
        types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
        types.InlineKeyboardButton("📊 آمار کامل", callback_data="admin_stats"),
        types.InlineKeyboardButton("💰 تایید پرداخت", callback_data="admin_approve"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")
    )
    
    bot.send_message(
        message.chat.id,
        "👑 پنل مدیریت:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_receipts")
def admin_receipts(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    try:
        with get_db() as conn:
            receipts = conn.execute('''
                SELECT * FROM receipts WHERE status = 'pending' ORDER BY created_at DESC
            ''').fetchall()
        
        if not receipts:
            bot.send_message(call.message.chat.id, "📸 فیش در انتظار نیست")
            return
        
        for r in receipts:
            text = f"🆔 {r['id']}\n👤 {r['user_id']}\n💰 {r['amount']:,} تومان\n🆔 {r['payment_code']}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_{r['id']}"),
                types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{r['id']}")
            )
            
            if os.path.exists(r['receipt_path']):
                with open(r['receipt_path'], 'rb') as f:
                    bot.send_photo(call.message.chat.id, f, caption=text, reply_markup=markup)
            else:
                bot.send_message(call.message.chat.id, text, reply_markup=markup)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_receipt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    try:
        receipt_id = int(call.data.replace('approve_', ''))
        
        with get_db() as conn:
            receipt = conn.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
            if receipt:
                conn.execute('''
                    UPDATE receipts SET status = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE id = ?
                ''', ('approved', datetime.now().isoformat(), call.from_user.id, receipt_id))
                
                conn.execute('''
                    UPDATE users SET payment_status = ?, payment_date = ?
                    WHERE user_id = ?
                ''', ('approved', datetime.now().isoformat(), receipt['user_id']))
                
                conn.commit()
                
                try:
                    bot.send_message(
                        receipt['user_id'],
                        f"✅ فیش شما تایید شد!\nاکنون می‌توانید ربات بسازید."
                    )
                except:
                    pass
        
        bot.answer_callback_query(call.id, "✅ تایید شد")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        bot.answer_callback_query(call.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_receipt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    try:
        receipt_id = int(call.data.replace('reject_', ''))
        
        with get_db() as conn:
            receipt = conn.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
            if receipt:
                conn.execute('''
                    UPDATE receipts SET status = ?, reviewed_at = ?, reviewed_by = ?
                    WHERE id = ?
                ''', ('rejected', datetime.now().isoformat(), call.from_user.id, receipt_id))
                conn.commit()
                
                try:
                    bot.send_message(
                        receipt['user_id'],
                        f"❌ فیش شما رد شد\nبا پشتیبانی تماس بگیرید: @shahraghee13"
                    )
                except:
                    pass
        
        bot.answer_callback_query(call.id, "❌ رد شد")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        bot.answer_callback_query(call.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def admin_users(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    try:
        with get_db() as conn:
            users = conn.execute('''
                SELECT user_id, username, first_name, bots_count, verified_referrals, 
                       payment_status, created_at
                FROM users ORDER BY created_at DESC LIMIT 20
            ''').fetchall()
        
        text = "👥 ۲۰ کاربر آخر:\n\n"
        for u in users:
            payment = "✅" if u['payment_status'] == 'approved' else "⏳"
            text += f"{payment} {u['user_id']} - {u['first_name']}\n"
            text += f"   🤖 {u['bots_count']} | 🎁 {u['verified_referrals']}\n\n"
        
        bot.send_message(call.message.chat.id, text)
    except:
        bot.send_message(call.message.chat.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    try:
        with get_db() as conn:
            total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
            total_bots = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
            running_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "running"').fetchone()[0]
            total_receipts = conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
            pending = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "pending"').fetchone()[0]
            approved = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "approved"').fetchone()[0]
            total_amount = conn.execute('SELECT SUM(amount) FROM receipts WHERE status = "approved"').fetchone()[0] or 0
            paid_users = conn.execute('SELECT COUNT(*) FROM users WHERE payment_status = "approved"').fetchone()[0]
        
        text = f"📊 آمار کامل\n"
        text += f"👥 کل کاربران: {total_users}\n"
        text += f"✅ پرداخت کرده: {paid_users}\n"
        text += f"🤖 کل ربات‌ها: {total_bots}\n"
        text += f"🟢 فعال: {running_bots}\n"
        text += f"📸 کل فیش‌ها: {total_receipts}\n"
        text += f"⏳ در انتظار: {pending}\n"
        text += f"✅ تایید شده: {approved}\n"
        text += f"💰 مجموع واریزی: {total_amount:,} تومان"
        
        bot.send_message(call.message.chat.id, text)
    except:
        bot.send_message(call.message.chat.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data == "admin_approve")
def admin_approve_prompt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "💰 آیدی کاربر را وارد کنید:"
    )
    bot.register_next_step_handler(msg, process_admin_approve)

def process_admin_approve(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ دسترسی ندارید!")
        return
    
    try:
        user_id = int(message.text.strip())
        
        with get_db() as conn:
            conn.execute('''
                UPDATE users SET payment_status = ?, payment_date = ?
                WHERE user_id = ?
            ''', ('approved', datetime.now().isoformat(), user_id))
            conn.commit()
        
        bot.reply_to(message, f"✅ پرداخت کاربر {user_id} تایید شد")
    except ValueError:
        bot.reply_to(message, "❌ آیدی باید عدد باشد")
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back(call):
    user_id = call.from_user.id
    is_admin = user_id in ADMIN_IDS
    markup = get_main_menu(is_admin)
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "🚀 منوی اصلی:", reply_markup=markup)

# ==================== مانیتورینگ ربات‌ها ====================
def monitor_bots():
    """بررسی دوره‌ای ربات‌های در حال اجرا"""
    while True:
        try:
            with get_db() as conn:
                running_bots = conn.execute('SELECT id, pid FROM bots WHERE status = "running"').fetchall()
                
                for bot in running_bots:
                    status = bot_engine.get_status(bot['id'])
                    if not status['running']:
                        conn.execute('UPDATE bots SET status = ? WHERE id = ?', ('stopped', bot['id']))
                        conn.commit()
                        logger.info(f"⚠️ ربات {bot['id']} متوقف شد")
            
            time.sleep(30)
        except Exception as e:
            logger.error(f"خطا در مانیتورینگ: {e}")
            time.sleep(60)

# شروع مانیتورینگ
monitor_thread = threading.Thread(target=monitor_bots, daemon=True)
monitor_thread.start()

# ==================== اجرا ====================
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 ربات مادر نهایی - نسخه فوق پیشرفته با موتور اجرا")
    print("=" * 60)
    print(f"✅ موتور اجرا: فعال")
    print(f"✅ کتابخانه منیجر: فعال")
    print(f"✅ ادمین: {ADMIN_IDS}")
    print(f"✅ پوشه فایل‌ها: {FILES_DIR}")
    print("=" * 60)
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"خطا: {e}")
            time.sleep(5)
