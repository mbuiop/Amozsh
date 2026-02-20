#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر نهایی - نسخه 7.0 پیشرفته
با موتور قدرتمند، امنیت بالا و سیستم پرداخت خودکار
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
import string
import base64
import hmac
from datetime import datetime, timedelta
import logging
from logging.handlers import RotatingFileHandler
import importlib
import pkg_resources
from pathlib import Path
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2

# ==================== تنظیمات پایه ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
FILES_DIR = os.path.join(BASE_DIR, "user_files")
RUNNING_DIR = os.path.join(BASE_DIR, "running_bots")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
RECEIPTS_DIR = os.path.join(BASE_DIR, "receipts")
ENCRYPTED_TOKENS_DIR = os.path.join(BASE_DIR, "encrypted_tokens")

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(RUNNING_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)
os.makedirs(ENCRYPTED_TOKENS_DIR, exist_ok=True)

# ==================== توکن ربات مادر ====================
BOT_TOKEN = "8541672444:AAF4PBn7-XqiXUgaK0arVajyZfcMWqbxSJ0"
bot = telebot.TeleBot(BOT_TOKEN)
bot.delete_webhook()

# ==================== آیدی ادمین ====================
ADMIN_IDS = [327855654]

# ==================== اطلاعات کارت (مخفی در کد) ====================
CARD_NUMBER = "5892101187322777"
CARD_HOLDER = "مرتضی نیکخو خنجری"  # این نام به کاربر نمایش داده نمی‌شود
PRICE = 2000000  # 2 میلیون تومان

# ==================== کلید رمزنگاری ====================
ENCRYPTION_KEY = base64.urlsafe_b64encode(os.urandom(32))
cipher = Fernet(ENCRYPTION_KEY)

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
    
    # جدول ربات‌ها با رمزنگاری توکن
    conn.execute('''
        CREATE TABLE IF NOT EXISTS bots (
            id TEXT PRIMARY KEY,
            user_id INTEGER,
            encrypted_token TEXT,
            token_hash TEXT UNIQUE,
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
    
    # جدول کتابخانه‌های نصب شده
    conn.execute('''
        CREATE TABLE IF NOT EXISTS installed_libraries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            library_name TEXT,
            version TEXT,
            installed_at TIMESTAMP,
            UNIQUE(user_id, library_name)
        )
    ''')
    
    # جدول صف ساخت
    conn.execute('''
        CREATE TABLE IF NOT EXISTS build_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            bot_id TEXT,
            folders TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.commit()

# ==================== سیستم رمزنگاری توکن ====================
class TokenEncryption:
    """رمزنگاری پیشرفته توکن‌های ربات"""
    
    @staticmethod
    def encrypt_token(token):
        """رمزنگاری توکن"""
        try:
            encrypted = cipher.encrypt(token.encode())
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            return encrypted.decode(), token_hash
        except Exception as e:
            logger.error(f"خطا در رمزنگاری توکن: {e}")
            return None, None
    
    @staticmethod
    def decrypt_token(encrypted_token):
        """رمزگشایی توکن"""
        try:
            decrypted = cipher.decrypt(encrypted_token.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"خطا در رمزگشایی توکن: {e}")
            return None
    
    @staticmethod
    def verify_token(token, token_hash):
        """تایید صحت توکن"""
        return hmac.compare_digest(
            hashlib.sha256(token.encode()).hexdigest(),
            token_hash
        )

# ==================== موتور کتابخانه‌ها ====================
class LibraryManager:
    """مدیریت پیشرفته نصب کتابخانه‌ها"""
    
    def __init__(self):
        self.common_libs = {
            'flask': 'Flask',
            'django': 'Django',
            'fastapi': 'fastapi',
            'aiohttp': 'aiohttp',
            'requests': 'requests',
            'httpx': 'httpx',
            'pyTelegramBotAPI': 'pyTelegramBotAPI',
            'aiogram': 'aiogram',
            'python-telegram-bot': 'python-telegram-bot',
            'sqlalchemy': 'SQLAlchemy',
            'psycopg2': 'psycopg2-binary',
            'pymysql': 'pymysql',
            'redis': 'redis',
            'pymongo': 'pymongo',
            'numpy': 'numpy',
            'pandas': 'pandas',
            'scipy': 'scipy',
            'matplotlib': 'matplotlib',
            'seaborn': 'seaborn',
            'plotly': 'plotly',
            'sklearn': 'scikit-learn',
            'tensorflow': 'tensorflow',
            'torch': 'torch',
            'keras': 'keras',
            'opencv': 'opencv-python',
            'pillow': 'Pillow',
            'pydub': 'pydub',
            'moviepy': 'moviepy',
            'bs4': 'beautifulsoup4',
            'selenium': 'selenium',
            'scrapy': 'Scrapy',
            'pypdf2': 'PyPDF2',
            'openpyxl': 'openpyxl',
            'cryptography': 'cryptography',
            'jwt': 'PyJWT',
            'jdatetime': 'jdatetime',
            'pytz': 'pytz',
            'yt-dlp': 'yt-dlp',
            'qrcode': 'qrcode[pil]',
            'psutil': 'psutil',
            'loguru': 'loguru',
        }
        
        self.installed = self.get_installed_libs()
    
    def get_installed_libs(self):
        """دریافت لیست کتابخانه‌های نصب شده"""
        installed = {}
        try:
            for dist in pkg_resources.working_set:
                installed[dist.project_name.lower()] = dist.version
        except:
            pass
        return installed
    
    def install_library(self, lib_name, user_id=None):
        """نصب کتابخانه با قابلیت پیگیری"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", lib_name],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                self.installed = self.get_installed_libs()
                
                # ذخیره در دیتابیس
                if user_id:
                    with get_db() as conn:
                        conn.execute('''
                            INSERT OR REPLACE INTO installed_libraries 
                            (user_id, library_name, version, installed_at)
                            VALUES (?, ?, ?, ?)
                        ''', (user_id, lib_name, self.installed.get(lib_name.lower(), 'unknown'), 
                              datetime.now().isoformat()))
                        conn.commit()
                
                return True, "نصب موفق"
            else:
                return False, result.stderr
                
        except subprocess.TimeoutExpired:
            return False, "زمان نصب بیش از حد طول کشید"
        except Exception as e:
            return False, str(e)
    
    def install_user_library(self, message):
        """نصب کتابخانه دلخواه کاربر"""
        user_id = message.from_user.id
        lib_name = message.text.strip()
        
        status_msg = bot.reply_to(message, f"🔄 در حال نصب {lib_name}...")
        
        success, msg = self.install_library(lib_name, user_id)
        
        if success:
            bot.edit_message_text(
                f"✅ کتابخانه {lib_name} با موفقیت نصب شد.",
                message.chat.id,
                status_msg.message_id
            )
        else:
            bot.edit_message_text(
                f"❌ خطا در نصب {lib_name}:\n```\n{msg[:200]}...\n```",
                message.chat.id,
                status_msg.message_id,
                parse_mode="Markdown"
            )

library_manager = LibraryManager()

# ==================== توابع کمکی ====================

def generate_secure_referral_code(user_id):
    """تولید کد رفرال امن و یکتا"""
    timestamp = str(int(time.time()))
    random_part = secrets.token_hex(4)
    unique_string = f"{user_id}{timestamp}{random_part}"
    return hashlib.sha256(unique_string.encode()).hexdigest()[:10]

def get_user(user_id):
    with get_db() as conn:
        user = conn.execute(
            'SELECT * FROM users WHERE user_id = ?',
            (user_id,)
        ).fetchone()
        return dict(user) if user else None

def create_user(user_id, username, first_name, last_name, referred_by=None):
    with get_db() as conn:
        now = datetime.now().isoformat()
        
        # تولید کد رفرال یکتا و امن
        referral_code = generate_secure_referral_code(user_id)
        
        conn.execute('''
            INSERT OR IGNORE INTO users 
            (user_id, username, first_name, last_name, referral_code, referred_by, created_at, last_active, payment_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name, referral_code, referred_by, now, now, 'pending'))
        
        conn.execute('''
            UPDATE users SET last_active = ? WHERE user_id = ?
        ''', (now, user_id))
        conn.commit()
        
        # اگه کاربر با رفرال اومده بود
        if referred_by:
            conn.execute('''
                UPDATE users SET referrals_count = referrals_count + 1
                WHERE user_id = ?
            ''', (referred_by,))
            conn.commit()
            
            # بررسی برای تایید رفرال (وقتی کاربر جدید ربات بسازه)
            # این تابع بعداً در ساخت ربات صدا زده می‌شه

def check_payment_status(user_id):
    """بررسی وضعیت پرداخت کاربر"""
    with get_db() as conn:
        user = conn.execute('SELECT payment_status FROM users WHERE user_id = ?', (user_id,)).fetchone()
        if user and user['payment_status'] == 'approved':
            return True
        
        # بررسی فیش‌های تایید شده
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

def add_bot(user_id, bot_id, token, name, username, file_path, folder_path=None, pid=None):
    """افزودن ربات با رمزنگاری توکن"""
    with get_db() as conn:
        now = datetime.now().isoformat()
        status = 'running' if pid else 'stopped'
        
        # رمزنگاری توکن
        encrypted_token, token_hash = TokenEncryption.encrypt_token(token)
        
        if not encrypted_token:
            return False
        
        conn.execute('''
            INSERT INTO bots 
            (id, user_id, encrypted_token, token_hash, name, username, file_path, folder_path, pid, status, created_at, last_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (bot_id, user_id, encrypted_token, token_hash, name, username, file_path, folder_path, pid, status, now, now))
        
        conn.execute('''
            UPDATE users SET bots_count = bots_count + 1, last_active = ?
            WHERE user_id = ?
        ''', (now, user_id))
        conn.commit()
        
        # به‌روزرسانی رفرال‌های verified
        user = conn.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,)).fetchone()
        if user and user['referred_by']:
            conn.execute('''
                UPDATE users SET verified_referrals = verified_referrals + 1
                WHERE user_id = ?
            ''', (user['referred_by'],))
            conn.commit()
        
        return True

def get_bot_token(bot_id):
    """دریافت توکن رمزگشایی شده ربات"""
    with get_db() as conn:
        bot_data = conn.execute('SELECT encrypted_token, token_hash FROM bots WHERE id = ?', (bot_id,)).fetchone()
        if bot_data:
            token = TokenEncryption.decrypt_token(bot_data['encrypted_token'])
            if token and TokenEncryption.verify_token(token, bot_data['token_hash']):
                return token
    return None

# ==================== موتور اجرای پیشرفته ربات ====================
class BotExecutionEngine:
    """موتور قدرتمند اجرای ربات‌ها با امنیت بالا"""
    
    @staticmethod
    def validate_code(code):
        """اعتبارسنجی کد با آنالیز امنیتی"""
        try:
            # بررسی نحوی
            compile(code, '<string>', 'exec')
            
            # بررسی کدهای مخرب
            dangerous_patterns = [
                r'os\.system\(',
                r'subprocess\.',
                r'__import__\(',
                r'eval\(',
                r'exec\(',
                r'open\(.*,\s*[\'"]w[\'"]\)',
                r'shutil\.rmtree',
                r'os\.remove',
            ]
            
            for pattern in dangerous_patterns:
                if re.search(pattern, code):
                    return False, "کد حاوی دستورات خطرناک است!"
            
            return True, None
            
        except SyntaxError as e:
            return False, str(e)
    
    @staticmethod
    def create_secure_environment(bot_id, user_id, code):
        """ایجاد محیط امن برای اجرای ربات"""
        bot_run_dir = os.path.join(RUNNING_DIR, bot_id)
        os.makedirs(bot_run_dir, exist_ok=True)
        
        # ایجاد فایل کد با هدر امنیتی
        secure_code = f"""#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot ID: {bot_id}
# User ID: {user_id}
# Created: {datetime.now().isoformat()}

import sys
import os
import signal
import logging

# تنظیمات امنیتی
sys.dont_write_bytecode = True
os.umask(0o077)

{code}

if __name__ == "__main__":
    try:
        # اجرای اصلی ربات
        main()
    except Exception as e:
        logging.error(f"Error in bot: {{e}}")
        sys.exit(1)
"""
        
        bot_file = os.path.join(bot_run_dir, f"{bot_id}.py")
        with open(bot_file, 'w', encoding='utf-8') as f:
            f.write(secure_code)
        
        return bot_file
    
    @staticmethod
    def run_bot_process(bot_id, token, code, user_id):
        """اجرای ربات با مانیتورینگ کامل"""
        try:
            # ایجاد محیط امن
            bot_file = BotExecutionEngine.create_secure_environment(bot_id, user_id, code)
            
            # ذخیره توکن رمزنگاری شده
            encrypted_token, _ = TokenEncryption.encrypt_token(token)
            token_file = os.path.join(os.path.dirname(bot_file), "token.enc")
            with open(token_file, 'w') as f:
                f.write(encrypted_token)
            
            # فایل لاگ
            log_file = os.path.join(os.path.dirname(bot_file), "bot.log")
            
            # اجرا با محدودیت منابع
            process = subprocess.Popen(
                [sys.executable, bot_file],
                stdout=open(log_file, 'a'),
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(bot_file),
                start_new_session=True,
                env={
                    'PYTHONPATH': os.path.dirname(bot_file),
                    'PYTHONUNBUFFERED': '1'
                }
            )
            
            logger.info(f"✅ ربات {bot_id} با PID {process.pid} اجرا شد")
            return process.pid
            
        except Exception as e:
            logger.error(f"خطا در اجرای ربات {bot_id}: {e}")
            return None
    
    @staticmethod
    def stop_bot_process(pid):
        """توقف ایمن فرآیند ربات"""
        try:
            # ارسال SIGTERM به کل گروه فرآیند
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            
            # منتظر می‌مانیم تا فرآیند بسته شود
            time.sleep(2)
            
            # اگر هنوز زنده بود، SIGKILL
            try:
                os.kill(pid, 0)
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except:
                pass
            
            return True
        except:
            return False
    
    @staticmethod
    def get_bot_status(pid):
        """دریافت وضعیت ربات در حال اجرا"""
        try:
            process = psutil.Process(pid)
            if process.is_running():
                cpu = process.cpu_percent(interval=0.1)
                memory = process.memory_percent()
                return {
                    'running': True,
                    'cpu': cpu,
                    'memory': memory,
                    'create_time': datetime.fromtimestamp(process.create_time())
                }
        except:
            pass
        return {'running': False}

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

# ==================== هندلرهای ربات ====================

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    last_name = message.from_user.last_name or ""
    
    # بررسی کد رفرال
    referred_by = None
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        with get_db() as conn:
            referrer = conn.execute('SELECT user_id FROM users WHERE referral_code = ?', (ref_code,)).fetchone()
            if referrer:
                referred_by = referrer['user_id']
                
                # ارسال پیام به رفرال کننده
                try:
                    bot.send_message(
                        referred_by,
                        f"🎉 **یک نفر با لینک رفرال شما وارد شد!**\n\n"
                        f"👤 کاربر جدید: {first_name}\n"
                        f"🆔 آیدی: {user_id}\n\n"
                        f"📊 آمار شما:\n"
                        f"• کلیک‌ها: +۱\n"
                        f"• وقتی این کاربر ربات بسازه، رفرال verified ثبت میشه"
                    )
                except:
                    pass
    
    create_user(user_id, username, first_name, last_name, referred_by)
    
    # ساخت لینک رفرال اختصاصی
    bot_username = bot.get_me().username
    user = get_user(user_id)
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    is_admin = user_id in ADMIN_IDS
    markup = get_main_menu(is_admin)
    
    welcome_text = (
        f"🚀 **به ربات مادر نهایی خوش آمدید {first_name}!**\n\n"
        f"👤 آیدی شما: `{user_id}`\n"
        f"🎁 **کد رفرال اختصاصی شما:**\n"
        f"`{user['referral_code']}`\n"
        f"🔗 لینک دعوت:\n"
        f"{referral_link}\n\n"
        f"📊 آمار رفرال شما:\n"
        f"• کلیک‌ها: {user['referrals_count']}\n"
        f"• ساخته شده: {user['verified_referrals']}\n\n"
        f"💡 هر ۵ نفر که ربات بسازند = ۱ ربات اضافه\n"
        f"📤 فایل `.py` خود را آپلود کنید تا رباتتان ساخته شود.\n"
        f"💡 برای راهنمایی کامل، گزینه '📚 راهنما' را بزنید."
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == '💰 کیف پول و رفرال')
def wallet_ref(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    # ساخت لینک رفرال
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    # بررسی وضعیت پرداخت
    payment_approved = check_payment_status(user_id)
    
    can_create, max_bots, current_bots = check_user_bot_limit(user_id)
    
    text = (
        f"💰 **کیف پول و سیستم رفرال**\n\n"
        f"👤 کاربر: {user['first_name']}\n"
        f"🆔 آیدی: `{user_id}`\n\n"
        f"💳 **وضعیت پرداخت:**\n"
        f"{'✅ تایید شده' if payment_approved else '⏳ در انتظار تایید'}\n\n"
        f"🎁 **کد رفرال شما:**\n"
        f"`{user['referral_code']}`\n"
        f"🔗 لینک دعوت:\n"
        f"{referral_link}\n\n"
        f"📊 **آمار رفرال:**\n"
        f"• کلیک‌ها: {user['referrals_count']}\n"
        f"• ساخته شده: {user['verified_referrals']}\n\n"
        f"🤖 **ربات‌ها:**\n"
        f"• فعلی: {current_bots}\n"
        f"• حداکثر: {max_bots}\n"
        f"• هر ۵ نفر که ربات بسازند = ۱ ربات اضافه\n\n"
    )
    
    if not payment_approved:
        text += (
            f"💳 **برای ساخت ربات جدید:**\n"
            f"مبلغ: {PRICE:,} تومان\n"
            f"شماره کارت: `{CARD_NUMBER}`\n\n"
            f"📸 پس از واریز، تصویر فیش را ارسال کنید.\n"
            f"فیش شما توسط ادمین بررسی می‌شود."
        )
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    # بررسی تکراری نبودن
    with get_db() as conn:
        existing = conn.execute('''
            SELECT id FROM receipts 
            WHERE user_id = ? AND status = 'pending'
        ''', (user_id,)).fetchone()
        
        if existing:
            bot.reply_to(message, "⏳ شما یک فیش در انتظار بررسی دارید. لطفاً صبور باشید.")
            return
    
    # دریافت عکس
    file_info = bot.get_file(message.photo[-1].file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    
    # کد پیگیری یکتا
    payment_code = hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:10].upper()
    
    # ذخیره فیش
    receipt_path = os.path.join(RECEIPTS_DIR, f"{user_id}_{payment_code}.jpg")
    with open(receipt_path, 'wb') as f:
        f.write(downloaded_file)
    
    # ذخیره در دیتابیس
    with get_db() as conn:
        conn.execute('''
            INSERT INTO receipts (user_id, amount, receipt_path, created_at, payment_code)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, PRICE, receipt_path, datetime.now().isoformat(), payment_code))
        conn.commit()
    
    bot.reply_to(
        message,
        f"✅ **فیش واریزی شما دریافت شد.**\n\n"
        f"💰 مبلغ: {PRICE:,} تومان\n"
        f"🆔 کد پیگیری: `{payment_code}`\n\n"
        f"پس از بررسی توسط ادمین، دسترسی ساخت ربات برای شما فعال می‌شود.\n"
        f"⏳ زمان بررسی: حداکثر ۲۴ ساعت"
    )
    
    # اطلاع به ادمین
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(
                admin_id,
                f"📸 **فیش جدید واریزی**\n\n"
                f"👤 کاربر: {user_id}\n"
                f"👤 نام: {message.from_user.first_name}\n"
                f"💰 مبلغ: {PRICE:,} تومان\n"
                f"🆔 کد پیگیری: {payment_code}\n"
                f"🕐 زمان: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"برای بررسی به پنل ادمین بروید."
            )
        except:
            pass

@bot.message_handler(func=lambda m: m.text == '📦 نصب کتابخانه')
def install_library_prompt(message):
    user_id = message.from_user.id
    
    if not check_payment_status(user_id):
        bot.send_message(
            message.chat.id,
            f"❌ ابتدا باید هزینه ساخت ربات را پرداخت کنید.\n"
            f"از منوی '💰 کیف پول و رفرال' اقدام کنید."
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    # کتابخانه‌های پرکاربرد
    common_libs = [
        ("requests", "requests"),
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("flask", "flask"),
        ("django", "django"),
        ("pillow", "pillow"),
        ("beautifulsoup4", "bs4"),
    ]
    
    for name, callback in common_libs:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"install_lib_{callback}"))
    
    markup.add(types.InlineKeyboardButton("📦 نصب دلخواه", callback_data="install_custom"))
    
    bot.send_message(
        message.chat.id,
        "📦 **نصب کتابخانه**\n\n"
        "کتابخانه مورد نظر را انتخاب کنید یا گزینه نصب دلخواه را بزنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('install_lib_'))
def install_selected_library(call):
    lib = call.data.replace('install_lib_', '')
    user_id = call.from_user.id
    
    bot.answer_callback_query(call.id, f"در حال نصب {lib}...")
    
    msg = bot.send_message(call.message.chat.id, f"🔄 در حال نصب {lib}...")
    
    success, result = library_manager.install_library(lib, user_id)
    
    if success:
        bot.edit_message_text(
            f"✅ کتابخانه {lib} با موفقیت نصب شد.",
            call.message.chat.id,
            msg.message_id
        )
    else:
        bot.edit_message_text(
            f"❌ خطا در نصب {lib}:\n```\n{result[:200]}...\n```",
            call.message.chat.id,
            msg.message_id,
            parse_mode="Markdown"
        )

@bot.callback_query_handler(func=lambda call: call.data == "install_custom")
def install_custom_prompt(call):
    msg = bot.send_message(
        call.message.chat.id,
        "📦 **نام کتابخانه مورد نظر را وارد کنید:**\n"
        "(مثال: flask, django, numpy)"
    )
    bot.register_next_step_handler(msg, library_manager.install_user_library)

@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot(message):
    user_id = message.from_user.id
    
    # بررسی وضعیت پرداخت
    if not check_payment_status(user_id):
        bot.send_message(
            message.chat.id,
            f"❌ برای ساخت ربات باید ابتدا هزینه را پرداخت کنید.\n\n"
            f"💰 مبلغ: {PRICE:,} تومان\n"
            f"💳 شماره کارت: `{CARD_NUMBER}`\n\n"
            f"📸 پس از واریز، تصویر فیش را ارسال کنید.\n"
            f"یا از منوی '💰 کیف پول و رفرال' اقدام کنید."
        )
        return
    
    can_create, max_bots, current_bots = check_user_bot_limit(user_id)
    
    if not can_create:
        bot.send_message(
            message.chat.id,
            f"❌ شما به حداکثر تعداد ربات ({max_bots}) رسیده‌اید!\n\n"
            f"برای ساخت ربات جدید:\n"
            f"1️⃣ یکی از ربات‌های فعلی را حذف کنید\n"
            f"2️⃣ یا با دعوت دوستان، ربات اضافه بگیرید\n\n"
            f"رفرال‌های شما: {get_user(user_id)['verified_referrals']}"
        )
        return
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn1 = types.InlineKeyboardButton("📁 آپلود مستقیم فایل", callback_data="build_simple")
    btn2 = types.InlineKeyboardButton("📂 ساخت با پوشه", callback_data="build_folder")
    markup.add(btn1, btn2)
    
    bot.send_message(
        message.chat.id,
        "🤖 **ساخت ربات جدید**\n\n"
        "روش ساخت را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "build_simple")
def build_simple(call):
    bot.send_message(
        call.message.chat.id,
        "📤 **آپلود فایل**\n\n"
        "فایل `.py` یا `.zip` خود را ارسال کنید:\n\n"
        "✅ توکن داخل کد باشه (TOKEN = '...')\n"
        "✅ کتابخانه‌ها خودکار نصب می‌شوند\n"
        "✅ حجم فایل حداکثر ۵۰ مگابایت"
    )

@bot.message_handler(content_types=['document'])
def handle_build_file(message):
    user_id = message.from_user.id
    
    # بررسی مجدد پرداخت
    if not check_payment_status(user_id):
        bot.reply_to(
            message,
            f"❌ ابتدا باید هزینه ساخت ربات را پرداخت کنید.\n"
            f"از منوی '💰 کیف پول و رفرال' اقدام کنید."
        )
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
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره فایل
        file_path = save_uploaded_file(user_id, downloaded_file, file_name)
        
        main_code = ""
        
        if file_name.endswith('.zip'):
            # استخراج فایل‌های zip
            extract_dir = os.path.join(FILES_DIR, str(user_id), f"extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            
            py_files = extract_files_from_zip(file_path, extract_dir)
            for pf in py_files:
                if pf['name'] in ['bot.py', 'main.py', 'run.py']:
                    main_code = pf['content']
                    break
            
            if not main_code and py_files:
                main_code = py_files[0]['content']
            
            shutil.rmtree(extract_dir)
        
        else:  # فایل .py
            with open(file_path, 'r', encoding='utf-8') as f:
                main_code = f.read()
        
        if not main_code:
            bot.edit_message_text(
                "❌ هیچ فایل پایتونی پیدا نشد!",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # اعتبارسنجی کد
        is_valid, error = BotExecutionEngine.validate_code(main_code)
        if not is_valid:
            bot.edit_message_text(
                f"❌ خطا در کد:\n```\n{error}\n```",
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
        bot_id = hashlib.sha256(f"{user_id}{token}{time.time()}".encode()).hexdigest()[:12]
        
        bot.edit_message_text(
            "🚀 در حال اجرای ربات...",
            message.chat.id,
            status_msg.message_id
        )
        
        # اجرای ربات با موتور جدید
        pid = BotExecutionEngine.run_bot_process(bot_id, token, main_code, user_id)
        
        if pid:
            # ذخیره در دیتابیس
            add_bot(user_id, bot_id, token, bot_name, bot_username, file_path, None, pid)
            
            result_text = f"✅ **ربات با موفقیت ساخته و اجرا شد!** 🎉\n\n"
            result_text += f"🤖 نام: {bot_name}\n"
            result_text += f"🔗 لینک: https://t.me/{bot_username}\n"
            result_text += f"🆔 آیدی ربات: `{bot_id}`\n"
            result_text += f"🔄 PID: {pid}\n"
            result_text += f"📊 وضعیت: در حال اجرا\n\n"
            result_text += f"💡 از /bots برای مشاهده لیست ربات‌ها استفاده کن."
            
            bot.edit_message_text(
                result_text,
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
        # دریافت وضعیت دقیق ربات
        status_info = BotExecutionEngine.get_bot_status(b['pid']) if b['pid'] else {'running': False}
        
        status_emoji = "🟢" if status_info['running'] else "🔴"
        status_text = "در حال اجرا" if status_info['running'] else "متوقف"
        
        text = f"{status_emoji} **{b['name']}**\n"
        text += f"🔗 https://t.me/{b['username']}\n"
        text += f"🆔 `{b['id']}`\n"
        text += f"📊 وضعیت: {status_text}\n"
        
        if status_info['running']:
            text += f"💻 CPU: {status_info['cpu']:.1f}%\n"
            text += f"🧠 RAM: {status_info['memory']:.1f}%\n"
        
        text += f"📅 {b['created_at'][:10]}\n"
        
        bot.send_message(message.chat.id, text, parse_mode="Markdown")

# ==================== توابع کمکی بیشتر ====================

def save_uploaded_file(user_id, file_data, file_name):
    """ذخیره فایل آپلود شده"""
    user_dir = os.path.join(FILES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    timestamp = int(time.time())
    file_path = os.path.join(user_dir, f"{timestamp}_{file_name}")
    
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    return file_path

def extract_files_from_zip(zip_path, extract_to):
    """استخراج فایل‌های zip"""
    py_files = []
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(extract_to)
    
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

def get_user_bots(user_id):
    """دریافت لیست ربات‌های کاربر"""
    with get_db() as conn:
        bots = conn.execute('''
            SELECT * FROM bots WHERE user_id = ? ORDER BY created_at DESC
        ''', (user_id,)).fetchall()
        return [dict(bot) for bot in bots]

def get_bot(bot_id):
    """دریافت اطلاعات ربات"""
    with get_db() as conn:
        bot = conn.execute('SELECT * FROM bots WHERE id = ?', (bot_id,)).fetchone()
        return dict(bot) if bot else None

def update_bot_status(bot_id, status, pid=None):
    """به‌روزرسانی وضعیت ربات"""
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

def check_user_bot_limit(user_id):
    """بررسی محدودیت تعداد ربات"""
    with get_db() as conn:
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        if not user:
            return False, 1, 0
        
        # هر ۵ نفر رفرال verified = ۱ ربات اضافه
        extra_bots = user['verified_referrals'] // 5
        max_bots = 1 + extra_bots
        
        current_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE user_id = ?', (user_id,)).fetchone()[0]
        
        return current_bots < max_bots, max_bots, current_bots

def delete_bot(bot_id, user_id):
    """حذف کامل ربات"""
    with get_db() as conn:
        bot = conn.execute('SELECT * FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id)).fetchone()
        if not bot:
            return False
        
        # توقف ربات
        if bot['pid']:
            BotExecutionEngine.stop_bot_process(bot['pid'])
        
        # حذف فایل‌ها
        if bot['file_path'] and os.path.exists(bot['file_path']):
            os.remove(bot['file_path'])
        
        if bot['folder_path'] and os.path.exists(bot['folder_path']):
            shutil.rmtree(bot['folder_path'])
        
        # حذف پوشه اجرا
        bot_run_dir = os.path.join(RUNNING_DIR, bot_id)
        if os.path.exists(bot_run_dir):
            shutil.rmtree(bot_run_dir)
        
        # حذف از دیتابیس
        conn.execute('DELETE FROM bots WHERE id = ?', (bot_id,))
        conn.execute('UPDATE users SET bots_count = bots_count - 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        
        return True

# ==================== مانیتورینگ ربات‌ها ====================
def monitor_running_bots():
    """بررسی ربات‌های در حال اجرا"""
    while True:
        try:
            with get_db() as conn:
                running_bots = conn.execute('SELECT id, pid FROM bots WHERE status = "running"').fetchall()
                
                for bot in running_bots:
                    bot_id, pid = bot
                    status = BotExecutionEngine.get_bot_status(pid)
                    
                    if not status['running']:
                        conn.execute('UPDATE bots SET status = ? WHERE id = ?', ('stopped', bot_id))
                        conn.commit()
                        logger.info(f"⚠️ ربات {bot_id} متوقف شد")
            
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"خطا در مانیتورینگ: {e}")
            time.sleep(60)

# شروع مانیتورینگ
monitor_thread = threading.Thread(target=monitor_running_bots, daemon=True)
monitor_thread.start()

# ==================== سایر هندلرها ====================

@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def guide(message):
    user = get_user(message.from_user.id)
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    text = (
        "📚 **راهنمای کامل ربات مادر**\n\n"
        "═══════════════════════════════════\n\n"
        
        "**1️⃣ ساخت ربات جدید**\n"
        "• ابتدا هزینه را پرداخت کنید\n"
        f"• شماره کارت: `{CARD_NUMBER}`\n"
        "• فایل `.py` یا `.zip` را آپلود کنید\n"
        "• توکن باید داخل کد باشه\n\n"
        
        "**2️⃣ سیستم رفرال**\n"
        f"• کد شما: `{user['referral_code']}`\n"
        f"• لینک: {referral_link}\n"
        "• هر ۵ نفر = ۱ ربات اضافه\n\n"
        
        "**3️⃣ کتابخانه‌ها**\n"
        "• ۶۰+ کتابخانه پشتیبانی می‌شود\n"
        "• می‌توانید کتابخانه دلخواه نصب کنید\n"
        "• از منوی '📦 نصب کتابخانه' اقدام کنید\n\n"
        
        "**4️⃣ مدیریت ربات‌ها**\n"
        "• /bots - لیست ربات‌ها\n"
        "• /stop [bot_id] - توقف\n"
        "• /resume [bot_id] - راه‌اندازی مجدد\n"
        "• /delete [bot_id] - حذف\n\n"
        
        "**5️⃣ پشتیبانی**\n"
        "• @shahraghee13\n"
        "• ۲۴ ساعته پاسخگو هستیم\n\n"
        
        "═══════════════════════════════════"
    )
    
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
    
    if BotExecutionEngine.stop_bot_process(bot_info['pid']):
        update_bot_status(bot_id, 'stopped')
        bot.reply_to(message, f"✅ ربات {bot_info['name']} متوقف شد.")
    else:
        bot.reply_to(message, "❌ خطا در توقف ربات!")

@bot.message_handler(commands=['resume'])
def cmd_resume(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ لطفاً آیدی ربات را وارد کنید:\n/resume bot_id")
        return
    
    bot_id = parts[1]
    user_id = message.from_user.id
    
    bot_info = get_bot(bot_id)
    
    if not bot_info or bot_info['user_id'] != user_id:
        bot.reply_to(message, "❌ ربات پیدا نشد یا مالک آن نیستید!")
        return
    
    # دریافت توکن رمزگشایی شده
    token = get_bot_token(bot_id)
    if not token:
        bot.reply_to(message, "❌ خطا در بازیابی توکن!")
        return
    
    # خواندن کد
    with open(bot_info['file_path'], 'r', encoding='utf-8') as f:
        code = f.read()
    
    msg = bot.reply_to(message, "🔄 در حال راه‌اندازی مجدد ربات...")
    
    pid = BotExecutionEngine.run_bot_process(bot_id, token, code, user_id)
    
    if pid:
        update_bot_status(bot_id, 'running', pid)
        bot.edit_message_text(
            f"✅ ربات {bot_info['name']} با موفقیت راه‌اندازی شد.",
            message.chat.id,
            msg.message_id
        )
    else:
        bot.edit_message_text(
            "❌ خطا در راه‌اندازی ربات!",
            message.chat.id,
            msg.message_id
        )

@bot.message_handler(commands=['delete'])
def cmd_delete(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ لطفاً آیدی ربات را وارد کنید:\n/delete bot_id")
        return
    
    bot_id = parts[1]
    user_id = message.from_user.id
    
    if delete_bot(bot_id, user_id):
        bot.reply_to(message, f"✅ ربات {bot_id} با موفقیت حذف شد.")
    else:
        bot.reply_to(message, "❌ خطا در حذف ربات!")

@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    cmd_bots(message)

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
        "🔄 **فعال/غیرفعال کردن ربات**\n\n"
        "ربات مورد نظر را انتخاب کنید:",
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
        # توقف
        if BotExecutionEngine.stop_bot_process(bot_info['pid']):
            update_bot_status(bot_id, 'stopped')
            bot.answer_callback_query(call.id, "✅ ربات متوقف شد")
            bot.edit_message_text(
                f"✅ ربات {bot_info['name']} متوقف شد.\n"
                f"برای فعال‌سازی مجدد از /resume {bot_id} استفاده کنید.",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.answer_callback_query(call.id, "❌ خطا در توقف!")
    
    else:
        # راه‌اندازی مجدد
        token = get_bot_token(bot_id)
        if not token:
            bot.answer_callback_query(call.id, "❌ خطا در بازیابی توکن!")
            return
        
        with open(bot_info['file_path'], 'r', encoding='utf-8') as f:
            code = f.read()
        
        pid = BotExecutionEngine.run_bot_process(bot_id, token, code, user_id)
        
        if pid:
            update_bot_status(bot_id, 'running', pid)
            bot.answer_callback_query(call.id, "✅ ربات فعال شد")
            bot.edit_message_text(
                f"✅ ربات {bot_info['name']} با موفقیت فعال شد.",
                call.message.chat.id,
                call.message.message_id
            )
        else:
            bot.answer_callback_query(call.id, "❌ خطا در فعال‌سازی!")

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
        "⚠️ **حذف ربات**\n\n"
        "⚠️ توجه: پس از حذف، امکان بازیابی وجود ندارد!\n\n"
        "ربات مورد نظر را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_'))
def confirm_delete(call):
    bot_id = call.data.replace('delete_', '')
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("✅ بله، حذف شود", callback_data=f"confirm_delete_{bot_id}")
    btn2 = types.InlineKeyboardButton("❌ انصراف", callback_data="cancel_delete")
    markup.add(btn1, btn2)
    
    bot.edit_message_text(
        "⚠️ **آیا از حذف این ربات اطمینان دارید؟**\n"
        "این عمل غیرقابل بازگشت است!",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_delete_'))
def do_delete(call):
    bot_id = call.data.replace('confirm_delete_', '')
    user_id = call.from_user.id
    
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

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_delete')
def cancel_delete(call):
    bot.edit_message_text(
        "❌ عملیات حذف لغو شد.",
        call.message.chat.id,
        call.message.message_id
    )

@bot.message_handler(func=lambda m: m.text == '📊 آمار')
def stats(message):
    with get_db() as conn:
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_bots = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
        running_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "running"').fetchone()[0]
        total_payments = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "approved"').fetchone()[0]
    
    text = f"📊 **آمار ربات**\n\n"
    text += f"👥 کاربران: {total_users:,}\n"
    text += f"🤖 کل ربات‌ها: {total_bots:,}\n"
    text += f"🟢 فعال: {running_bots:,}\n"
    text += f"💰 پرداخت‌ها: {total_payments:,}"
    
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(
        message.chat.id,
        "📞 **پشتیبانی**\n\n"
        "برای ارتباط با پشتیبانی:\n"
        "• @shahraghee13\n"
        "• ۲۴ ساعته پاسخگو هستیم\n\n"
        "🌐 **کانال اعلانات:**\n"
        "@channel"
    )

# ==================== پنل ادمین ====================

@bot.message_handler(func=lambda m: m.text == '👑 پنل ادمین')
def admin_panel(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ شما دسترسی ادمین ندارید!")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 پیام همگانی", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("📸 مشاهده فیش‌ها", callback_data="admin_receipts"),
        types.InlineKeyboardButton("👥 لیست کاربران", callback_data="admin_users"),
        types.InlineKeyboardButton("🗑 حذف کاربر", callback_data="admin_delete_user"),
        types.InlineKeyboardButton("📊 آمار کامل", callback_data="admin_stats"),
        types.InlineKeyboardButton("💰 تایید پرداخت", callback_data="admin_approve_payment"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")
    )
    
    bot.send_message(
        message.chat.id,
        "👑 **پنل مدیریت**\n\n"
        "یکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_receipts")
def admin_receipts(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    show_receipts_page(call.message, 1)

def show_receipts_page(message, page):
    per_page = 5
    offset = (page - 1) * per_page
    
    with get_db() as conn:
        receipts = conn.execute('''
            SELECT * FROM receipts WHERE status = 'pending' 
            ORDER BY created_at DESC LIMIT ? OFFSET ?
        ''', (per_page, offset)).fetchall()
        
        total = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "pending"').fetchone()[0]
    
    if not receipts:
        bot.send_message(message.chat.id, "📸 هیچ فیش در انتظاری وجود ندارد.")
        return
    
    text = f"📸 **فیش‌های در انتظار (صفحه {page} از {(total-1)//per_page+1})**\n\n"
    
    for r in receipts:
        text += f"🆔 **فیش {r['id']}**\n"
        text += f"👤 کاربر: {r['user_id']}\n"
        text += f"💰 مبلغ: {r['amount']:,} تومان\n"
        text += f"🆔 کد: {r['payment_code']}\n"
        text += f"🕐 {r['created_at'][:16]}\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_{r['id']}"),
            types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{r['id']}")
        )
        
        # ارسال عکس فیش
        if os.path.exists(r['receipt_path']):
            with open(r['receipt_path'], 'rb') as f:
                bot.send_photo(message.chat.id, f, caption=text, reply_markup=markup)
        else:
            bot.send_message(message.chat.id, text, reply_markup=markup)
        
        text = ""  # برای فیش‌های بعدی، متن تکراری نباشه

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_receipt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    receipt_id = int(call.data.replace('approve_', ''))
    
    with get_db() as conn:
        receipt = conn.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
        if receipt:
            conn.execute('''
                UPDATE receipts SET status = ?, reviewed_at = ?, reviewed_by = ?
                WHERE id = ?
            ''', ('approved', datetime.now().isoformat(), call.from_user.id, receipt_id))
            
            # آپدیت وضعیت پرداخت کاربر
            conn.execute('''
                UPDATE users SET payment_status = ?, payment_date = ?
                WHERE user_id = ?
            ''', ('approved', datetime.now().isoformat(), receipt['user_id']))
            
            conn.commit()
            
            # اطلاع به کاربر
            try:
                bot.send_message(
                    receipt['user_id'],
                    f"✅ **فیش واریزی شما تایید شد!**\n\n"
                    f"💰 مبلغ: {receipt['amount']:,} تومان\n"
                    f"🆔 کد پیگیری: {receipt['payment_code']}\n\n"
                    f"اکنون می‌توانید از منوی اصلی ربات خود را بسازید."
                )
            except:
                pass
    
    bot.answer_callback_query(call.id, "✅ فیش تایید شد")
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_receipt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    receipt_id = int(call.data.replace('reject_', ''))
    
    with get_db() as conn:
        receipt = conn.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
        if receipt:
            conn.execute('''
                UPDATE receipts SET status = ?, reviewed_at = ?, reviewed_by = ?
                WHERE id = ?
            ''', ('rejected', datetime.now().isoformat(), call.from_user.id, receipt_id))
            conn.commit()
            
            # اطلاع به کاربر
            try:
                bot.send_message(
                    receipt['user_id'],
                    f"❌ **فیش واریزی شما رد شد!**\n\n"
                    f"💰 مبلغ: {receipt['amount']:,} تومان\n"
                    f"🆔 کد پیگیری: {receipt['payment_code']}\n\n"
                    f"لطفاً با پشتیبانی تماس بگیرید: @shahraghee13"
                )
            except:
                pass
    
    bot.answer_callback_query(call.id, "❌ فیش رد شد")
    bot.delete_message(call.message.chat.id, call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def admin_users(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    with get_db() as conn:
        users = conn.execute('''
            SELECT user_id, username, first_name, bots_count, verified_referrals, 
                   payment_status, created_at
            FROM users ORDER BY created_at DESC LIMIT 20
        ''').fetchall()
    
    text = "👥 **۲۰ کاربر آخر**\n\n"
    for u in users:
        payment_emoji = "✅" if u['payment_status'] == 'approved' else "⏳"
        text += f"{payment_emoji} 🆔 {u['user_id']}\n"
        text += f"👤 {u['first_name']} (@{u['username']})\n"
        text += f"🤖 {u['bots_count']} | 🎁 {u['verified_referrals']}\n"
        text += f"📅 {u['created_at'][:16]}\n\n"
    
    bot.send_message(call.message.chat.id, text)

@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    with get_db() as conn:
        total_users = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        total_bots = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
        running_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE status = "running"').fetchone()[0]
        total_receipts = conn.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
        pending_receipts = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "pending"').fetchone()[0]
        approved_receipts = conn.execute('SELECT COUNT(*) FROM receipts WHERE status = "approved"').fetchone()[0]
        total_amount = conn.execute('SELECT SUM(amount) FROM receipts WHERE status = "approved"').fetchone()[0] or 0
        paid_users = conn.execute('SELECT COUNT(*) FROM users WHERE payment_status = "approved"').fetchone()[0]
    
    text = "📊 **آمار کامل سیستم**\n\n"
    text += f"👥 کل کاربران: {total_users:,}\n"
    text += f"✅ کاربران پرداخت‌کننده: {paid_users:,}\n"
    text += f"🤖 کل ربات‌ها: {total_bots:,}\n"
    text += f"🟢 ربات‌های فعال: {running_bots:,}\n\n"
    text += f"📸 کل فیش‌ها: {total_receipts}\n"
    text += f"⏳ در انتظار: {pending_receipts}\n"
    text += f"✅ تایید شده: {approved_receipts}\n"
    text += f"💰 مجموع واریزی: {total_amount:,} تومان\n"
    
    bot.send_message(call.message.chat.id, text)

@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back(call):
    user_id = call.from_user.id
    is_admin = user_id in ADMIN_IDS
    markup = get_main_menu(is_admin)
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    
    bot.send_message(
        call.message.chat.id,
        "🚀 بازگشت به منوی اصلی:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
def admin_broadcast(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "📢 **ارسال پیام همگانی**\n\n"
        "متن پیام را وارد کنید:"
    )
    bot.register_next_step_handler(msg, process_broadcast)

def process_broadcast(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ دسترسی ندارید!")
        return
    
    text = message.text
    
    with get_db() as conn:
        users = conn.execute('SELECT user_id FROM users').fetchall()
    
    sent = 0
    failed = 0
    
    status_msg = bot.reply_to(message, f"🔄 در حال ارسال به {len(users)} کاربر...")
    
    for user in users:
        try:
            bot.send_message(user['user_id'], text)
            sent += 1
        except:
            failed += 1
        
        if sent % 10 == 0:
            bot.edit_message_text(
                f"🔄 پیشرفت: {sent}/{len(users)}",
                message.chat.id,
                status_msg.message_id
            )
    
    bot.edit_message_text(
        f"✅ **ارسال پیام همگانی کامل شد**\n\n"
        f"✅ موفق: {sent}\n"
        f"❌ ناموفق: {failed}\n"
        f"👥 مجموع: {len(users)}",
        message.chat.id,
        status_msg.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_user")
def admin_delete_user(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "🗑 **آیدی عددی کاربر را برای حذف وارد کنید:**"
    )
    bot.register_next_step_handler(msg, process_delete_user)

def process_delete_user(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ دسترسی ندارید!")
        return
    
    try:
        user_id = int(message.text)
    except:
        bot.reply_to(message, "❌ آیدی باید عدد باشد!")
        return
    
    with get_db() as conn:
        # حذف ربات‌های کاربر
        bots = conn.execute('SELECT id, pid FROM bots WHERE user_id = ?', (user_id,)).fetchall()
        for b in bots:
            if b['pid']:
                try:
                    BotExecutionEngine.stop_bot_process(b['pid'])
                except:
                    pass
        
        # حذف از دیتابیس
        conn.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM bots WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM receipts WHERE user_id = ?', (user_id,))
        conn.commit()
    
    bot.reply_to(message, f"✅ کاربر {user_id} با تمام ربات‌هایش حذف شد.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_approve_payment")
def admin_approve_payment(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید!")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "💰 **آیدی عددی کاربر را برای تایید پرداخت وارد کنید:**\n"
        "(بدون نیاز به فیش)"
    )
    bot.register_next_step_handler(msg, process_approve_payment)

def process_approve_payment(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ دسترسی ندارید!")
        return
    
    try:
        user_id = int(message.text)
    except:
        bot.reply_to(message, "❌ آیدی باید عدد باشد!")
        return
    
    with get_db() as conn:
        conn.execute('''
            UPDATE users SET payment_status = ?, payment_date = ?
            WHERE user_id = ?
        ''', ('approved', datetime.now().isoformat(), user_id))
        conn.commit()
    
    bot.reply_to(message, f"✅ پرداخت کاربر {user_id} تایید شد.")

# ==================== اجرا ====================
if __name__ == "__main__":
    logger.info("🚀 ربات مادر نهایی نسخه 7.0 پیشرفته راه‌اندازی شد...")
    logger.info(f"📁 پوشه فایل‌ها: {FILES_DIR}")
    logger.info(f"📁 پوشه ربات‌های در حال اجرا: {RUNNING_DIR}")
    logger.info(f"📁 پوشه فیش‌ها: {RECEIPTS_DIR}")
    logger.info(f"🔐 رمزنگاری توکن: فعال")
    logger.info(f"📚 کتابخانه‌ها: {len(library_manager.common_libs)} عنوان")
    
    # پاکسازی لاگ‌های قدیمی
    try:
        subprocess.run(["find", LOGS_DIR, "-name", "*.log", "-mtime", "+30", "-delete"])
    except:
        pass
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            logger.error(f"خطا: {e}")
            time.sleep(5)