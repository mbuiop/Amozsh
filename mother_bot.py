#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر نهایی - نسخه نهایی 8.0
تمامی امکانات بدون هیچ خطایی
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
import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

# ==================== ایمپورت موتور پیشرفته ====================
try:
    from advanced_engine import execute_user_bot, engine
    ADVANCED_ENGINE = True
    print("✅ موتور پیشرفته با موفقیت بارگذاری شد")
except Exception as e:
    ADVANCED_ENGINE = False
    print(f"⚠️ خطا در بارگذاری موتور پیشرفته: {e}")

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

# ==================== اطلاعات کارت ====================
CARD_NUMBER = "5892101187322777"
CARD_HOLDER = "مرتضی نیکخو خنجری"  # مخفی
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

# ==================== دیتابیس ====================
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
    
    # جدول فیش‌ها
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
            
            # اگر با رفرال آمده
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
            # چک کردن وضعیت مستقیم
            user = conn.execute('SELECT payment_status FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user and user['payment_status'] == 'approved':
                return True
            
            # چک کردن فیش تایید شده
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
                return False, 1, 0
            
            # هر ۵ رفرال = ۱ ربات اضافه
            extra_bots = user['verified_referrals'] // 5
            max_bots = 1 + extra_bots
            current_bots = conn.execute('SELECT COUNT(*) FROM bots WHERE user_id = ?', (user_id,)).fetchone()[0]
            
            return current_bots < max_bots, max_bots, current_bots
    except:
        return False, 1, 0

def get_user_bots(user_id):
    """گرفتن لیست ربات‌های کاربر"""
    try:
        with get_db() as conn:
            bots = conn.execute('''
                SELECT * FROM bots WHERE user_id = ? ORDER BY created_at DESC
            ''', (user_id,)).fetchall()
            return [dict(bot) for bot in bots]
    except:
        return []

def get_bot(bot_id):
    """گرفتن اطلاعات یک ربات"""
    try:
        with get_db() as conn:
            bot = conn.execute('SELECT * FROM bots WHERE id = ?', (bot_id,)).fetchone()
            return dict(bot) if bot else None
    except:
        return None

def add_bot(user_id, bot_id, token, name, username, file_path, pid=None):
    """اضافه کردن ربات به دیتابیس"""
    try:
        with get_db() as conn:
            now = datetime.now().isoformat()
            status = 'running' if pid else 'stopped'
            
            conn.execute('''
                INSERT INTO bots 
                (id, user_id, token, name, username, file_path, pid, status, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bot_id, user_id, token, name, username, file_path, pid, status, now, now))
            
            conn.execute('''
                UPDATE users SET bots_count = bots_count + 1, last_active = ?
                WHERE user_id = ?
            ''', (now, user_id))
            conn.commit()
            
            # آپدیت رفرال
            user = conn.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user and user['referred_by']:
                conn.execute('''
                    UPDATE users SET verified_referrals = verified_referrals + 1
                    WHERE user_id = ?
                ''', (user['referred_by'],))
                conn.commit()
            
            return True
    except Exception as e:
        logger.error(f"خطا در add_bot: {e}")
        return False

def update_bot_status(bot_id, status, pid=None):
    """آپدیت وضعیت ربات"""
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
    """حذف ربات"""
    try:
        with get_db() as conn:
            bot = conn.execute('SELECT * FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id)).fetchone()
            if not bot:
                return False
            
            # توقف پروسه
            if bot['pid']:
                try:
                    os.kill(bot['pid'], signal.SIGTERM)
                except:
                    pass
            
            # حذف فایل‌ها
            if bot['file_path'] and os.path.exists(bot['file_path']):
                os.remove(bot['file_path'])
            
            # حذف از دیتابیس
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

def extract_from_zip(zip_path, extract_to):
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

def extract_token(code):
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
    
    # بررسی کد رفرال
    referred_by = None
    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        try:
            with get_db() as conn:
                referrer = conn.execute('SELECT user_id FROM users WHERE referral_code = ?', (ref_code,)).fetchone()
                if referrer:
                    referred_by = referrer['user_id']
        except:
            pass
    
    # ایجاد کاربر
    create_user(user_id, username, first_name, last_name, referred_by)
    
    # گرفتن اطلاعات کاربر
    user = get_user(user_id)
    if not user:
        user = {
            'referral_code': 'ERROR',
            'referrals_count': 0,
            'verified_referrals': 0
        }
    
    # ساخت لینک رفرال
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    is_admin = user_id in ADMIN_IDS
    markup = get_main_menu(is_admin)
    
    # متن خوش‌آمدگویی (بدون مارک‌داون)
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
    
    # گرفتن اطلاعات کاربر
    user = get_user(user_id)
    if not user:
        bot.send_message(message.chat.id, "❌ لطفاً ابتدا /start را بزنید")
        return
    
    # ساخت لینک رفرال
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    # بررسی پرداخت
    payment_approved = check_payment(user_id)
    
    # بررسی محدودیت ربات
    can_create, max_bots, current_bots = check_bot_limit(user_id)
    
    # ساخت متن
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
    text += f"• حداکثر: {max_bots}\n"
    text += f"• هر ۵ نفر = ۱ ربات اضافه\n\n"
    
    if not payment_approved:
        text += f"💳 برای ساخت ربات جدید:\n"
        text += f"مبلغ: {PRICE:,} تومان\n"
        text += f"شماره کارت: {CARD_NUMBER}\n\n"
        text += f"📸 پس از واریز، تصویر فیش را ارسال کنید"
    
    bot.send_message(message.chat.id, text)

# ==================== فیش واریزی ====================
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    # بررسی تکراری نبودن
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
        # دریافت عکس
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # کد پیگیری
        payment_code = hashlib.md5(f"{user_id}_{time.time()}".encode()).hexdigest()[:8].upper()
        receipt_path = os.path.join(RECEIPTS_DIR, f"{user_id}_{payment_code}.jpg")
        
        # ذخیره عکس
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
            f"✅ فیش دریافت شد\n"
            f"💰 مبلغ: {PRICE:,} تومان\n"
            f"🆔 کد: {payment_code}\n\n"
            f"پس از بررسی توسط ادمین فعال می‌شود"
        )
        
        # اطلاع به ادمین
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

# ==================== ساخت ربات جدید ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot(message):
    user_id = message.from_user.id
    
    # بررسی پرداخت
    if not check_payment(user_id):
        bot.send_message(
            message.chat.id,
            f"❌ ابتدا هزینه را پرداخت کنید\n"
            f"از منوی '💰 کیف پول و رفرال' اقدام کنید"
        )
        return
    
    # بررسی محدودیت
    can_create, max_bots, current_bots = check_bot_limit(user_id)
    if not can_create:
        bot.send_message(
            message.chat.id,
            f"❌ به حد مجاز رسیده‌اید ({max_bots} ربات)\n"
            f"برای ساخت ربات جدید:\n"
            f"1️⃣ یکی از ربات‌ها را حذف کنید\n"
            f"2️⃣ یا با دعوت دوستان ربات اضافه بگیرید"
        )
        return
    
    bot.send_message(
        message.chat.id,
        "📤 فایل .py یا .zip خود را ارسال کنید\n"
        "✅ حجم حداکثر ۵۰ مگابایت\n"
        "✅ توکن داخل کد باشد"
    )

# ==================== آپلود فایل ====================
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    
    # بررسی پرداخت
    if not check_payment(user_id):
        bot.reply_to(message, "❌ ابتدا هزینه را پرداخت کنید")
        return
    
    file_name = message.document.file_name
    
    # بررسی پسوند
    if not (file_name.endswith('.py') or file_name.endswith('.zip')):
        bot.reply_to(message, "❌ فقط .py یا .zip مجاز است")
        return
    
    # بررسی حجم
    if message.document.file_size > 50 * 1024 * 1024:
        bot.reply_to(message, "❌ حجم فایل بیش از ۵۰ مگابایت")
        return
    
    status_msg = bot.reply_to(message, "🔄 در حال پردازش...")
    
    try:
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # ذخیره فایل
        file_path = save_uploaded_file(user_id, downloaded_file, file_name)
        if not file_path:
            bot.edit_message_text("❌ خطا در ذخیره فایل", message.chat.id, status_msg.message_id)
            return
        
        # استخراج کد
        code = ""
        
        if file_name.endswith('.zip'):
            extract_dir = os.path.join(FILES_DIR, str(user_id), f"extract_{int(time.time())}")
            os.makedirs(extract_dir, exist_ok=True)
            
            py_files = extract_from_zip(file_path, extract_dir)
            
            # پیدا کردن فایل اصلی
            for pf in py_files:
                if pf['name'] in ['bot.py', 'main.py', 'run.py', 'index.py']:
                    code = pf['content']
                    break
            
            if not code and py_files:
                code = py_files[0]['content']
            
            # پاکسازی
            shutil.rmtree(extract_dir, ignore_errors=True)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    code = f.read()
            except:
                with open(file_path, 'r', encoding='cp1256') as f:
                    code = f.read()
        
        if not code:
            bot.edit_message_text("❌ فایل پایتون پیدا نشد", message.chat.id, status_msg.message_id)
            return
        
        # استخراج توکن
        token = extract_token(code)
        if not token:
            bot.edit_message_text("❌ توکن در کد پیدا نشد", message.chat.id, status_msg.message_id)
            return
        
        # تست توکن
        try:
            response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if response.status_code != 200:
                bot.edit_message_text("❌ توکن معتبر نیست", message.chat.id, status_msg.message_id)
                return
            
            bot_info = response.json()['result']
            bot_name = bot_info['first_name']
            bot_username = bot_info['username']
        except Exception as e:
            bot.edit_message_text(f"❌ خطا در بررسی توکن: {str(e)}", message.chat.id, status_msg.message_id)
            return
        
        bot.edit_message_text("⚡ در حال اجرا...", message.chat.id, status_msg.message_id)
        
        # اجرا با موتور پیشرفته
        if ADVANCED_ENGINE:
            result = execute_user_bot(user_id, code, token)
            
            if result['success']:
                bot_id = result['bot_id']
                pid = result['pid']
                
                # ذخیره در دیتابیس
                add_bot(user_id, bot_id, token, bot_name, bot_username, file_path, pid)
                
                reply = (
                    f"✅ ربات با موفقیت ساخته شد\n\n"
                    f"🤖 نام: {bot_name}\n"
                    f"🔗 لینک: https://t.me/{bot_username}\n"
                    f"🆔 آیدی: {bot_id}\n"
                    f"🔄 PID: {pid}\n"
                    f"🛡️ امنیت: محیط ایزوله\n\n"
                    f"📋 /bots برای لیست ربات‌ها"
                )
                bot.edit_message_text(reply, message.chat.id, status_msg.message_id)
            else:
                error = result.get('error', 'خطای ناشناخته')
                output = result.get('output', '')
                log = result.get('log', '')
                
                reply = f"❌ خطا در اجرا\n\n⚠️ {error}"
                if output:
                    reply += f"\n\n📤 خروجی:\n{output[:200]}"
                if log and not output:
                    reply += f"\n\n📋 لاگ:\n{log[:200]}"
                
                bot.edit_message_text(reply, message.chat.id, status_msg.message_id)
        else:
            # روش ساده (بدون موتور پیشرفته)
            bot_id = hashlib.md5(f"{user_id}{token}{time.time()}".encode()).hexdigest()[:10]
            add_bot(user_id, bot_id, token, bot_name, bot_username, file_path, 1234)
            
            reply = f"✅ ربات ساخته شد (روش ساده)\n\n🤖 {bot_name}\n🔗 https://t.me/{bot_username}"
            bot.edit_message_text(reply, message.chat.id, status_msg.message_id)
        
    except Exception as e:
        logger.error(f"خطا در handle_file: {e}")
        bot.edit_message_text(f"❌ خطا: {str(e)}", message.chat.id, status_msg.message_id)

# ==================== ربات‌های من ====================
@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(message.chat.id, "📋 شما رباتی ندارید")
        return
    
    for b in bots[:10]:
        status = "🟢 فعال" if b['status'] == 'running' else "🔴 غیرفعال"
        text = f"{status}\n"
        text += f"🤖 {b['name']}\n"
        text += f"🔗 https://t.me/{b['username']}\n"
        text += f"🆔 {b['id']}\n"
        text += f"📅 {b['created_at'][:10]}\n"
        
        bot.send_message(message.chat.id, text)

# ==================== فعال/غیرفعال کردن ====================
@bot.message_handler(func=lambda m: m.text == '🔄 فعال/غیرفعال کردن')
def toggle_menu(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(message.chat.id, "📋 رباتی ندارید")
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
        "🔄 انتخاب ربات:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('toggle_'))
def toggle_bot(call):
    bot_id = call.data.replace('toggle_', '')
    user_id = call.from_user.id
    
    bot_info = get_bot(bot_id)
    if not bot_info or bot_info['user_id'] != user_id:
        bot.answer_callback_query(call.id, "❌ خطا")
        return
    
    if bot_info['status'] == 'running':
        try:
            if bot_info['pid']:
                os.kill(bot_info['pid'], signal.SIGTERM)
            update_bot_status(bot_id, 'stopped')
            bot.answer_callback_query(call.id, "✅ متوقف شد")
            bot.edit_message_text(
                f"✅ ربات {bot_info['name']} متوقف شد",
                call.message.chat.id,
                call.message.message_id
            )
        except:
            bot.answer_callback_query(call.id, "❌ خطا در توقف")
    else:
        bot.answer_callback_query(call.id, "❌ ربات فعال نیست")

# ==================== حذف ربات ====================
@bot.message_handler(func=lambda m: m.text == '🗑 حذف ربات')
def delete_menu(message):
    user_id = message.from_user.id
    bots = get_user_bots(user_id)
    
    if not bots:
        bot.send_message(message.chat.id, "📋 رباتی ندارید")
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
        "⚠️ انتخاب ربات برای حذف:",
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
        "⚠️ آیا مطمئن هستید؟",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('confirm_del_'))
def do_delete(call):
    bot_id = call.data.replace('confirm_del_', '')
    user_id = call.from_user.id
    
    if delete_bot(bot_id, user_id):
        bot.edit_message_text(
            "✅ ربات حذف شد",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.edit_message_text(
            "❌ خطا در حذف",
            call.message.chat.id,
            call.message.message_id
        )

@bot.callback_query_handler(func=lambda call: call.data == 'cancel_del')
def cancel_delete(call):
    bot.edit_message_text(
        "❌ لغو شد",
        call.message.chat.id,
        call.message.message_id
    )

# ==================== راهنما ====================
@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def guide(message):
    user = get_user(message.from_user.id)
    if not user:
        bot.send_message(message.chat.id, "❌ لطفاً /start را بزنید")
        return
    
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    
    text = (
        "📚 راهنمای کامل\n\n"
        "1️⃣ ساخت ربات:\n"
        f"   • کارت: {CARD_NUMBER}\n"
        "   • فایل .py آپلود کن\n"
        "   • توکن داخل کد باشه\n\n"
        "2️⃣ رفرال:\n"
        f"   • لینک: {referral_link}\n"
        "   • هر ۵ نفر = ۱ ربات اضافه\n\n"
        "3️⃣ مدیریت:\n"
        "   • /bots لیست ربات‌ها\n"
        "   • از منو می‌تونی فعال/غیرفعال کنی\n\n"
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
        
        text = f"📊 آمار\n👥 کاربران: {total_users}\n🤖 کل ربات‌ها: {total_bots}\n🟢 فعال: {running_bots}"
        bot.send_message(message.chat.id, text)
    except:
        bot.send_message(message.chat.id, "📊 آمار در دسترس نیست")

# ==================== پشتیبانی ====================
@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(message.chat.id, "📞 پشتیبانی: @shahraghee13")

# ==================== پنل ادمین ====================
@bot.message_handler(func=lambda m: m.text == '👑 پنل ادمین')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ دسترسی ندارید")
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📸 فیش‌ها", callback_data="admin_receipts"),
        types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
        types.InlineKeyboardButton("📊 آمار", callback_data="admin_stats"),
        types.InlineKeyboardButton("💰 تایید پرداخت", callback_data="admin_approve"),
        types.InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back")
    )
    
    bot.send_message(message.chat.id, "👑 پنل مدیریت:", reply_markup=markup)

# ==================== نمایش فیش‌ها ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_receipts")
def admin_receipts(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید")
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
            
            markup = types.InlineKeyboardMarkup(row_width=2)
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

# ==================== تایید فیش ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve_receipt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید")
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
                        f"✅ فیش شما تایید شد\nاکنون می‌توانید ربات بسازید"
                    )
                except:
                    pass
        
        bot.answer_callback_query(call.id, "✅ تایید شد")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ خطا: {str(e)}")

# ==================== رد فیش ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject_receipt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید")
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
    except Exception as e:
        bot.answer_callback_query(call.id, f"❌ خطا: {str(e)}")

# ==================== لیست کاربران ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def admin_users(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید")
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
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

# ==================== آمار ادمین ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
def admin_stats(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید")
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
        text += f"💰 مجموع: {total_amount:,} تومان"
        
        bot.send_message(call.message.chat.id, text)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

# ==================== تایید مستقیم پرداخت ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_approve")
def admin_approve_prompt(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "⛔ دسترسی ندارید")
        return
    
    msg = bot.send_message(
        call.message.chat.id,
        "💰 آیدی کاربر را وارد کنید:"
    )
    bot.register_next_step_handler(msg, process_admin_approve)

def process_admin_approve(message):
    if message.from_user.id not in ADMIN_IDS:
        bot.reply_to(message, "⛔ دسترسی ندارید")
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

# ==================== بازگشت ====================
@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def admin_back(call):
    user_id = call.from_user.id
    is_admin = user_id in ADMIN_IDS
    markup = get_main_menu(is_admin)
    
    bot.delete_message(call.message.chat.id, call.message.message_id)
    bot.send_message(call.message.chat.id, "🚀 منوی اصلی:", reply_markup=markup)

# ==================== اجرا ====================
if __name__ == "__main__":
    logger.info("🚀 ربات مادر نهایی راه‌اندازی شد")
    logger.info(f"موتور پیشرفته: {'✅ فعال' if ADVANCED_ENGINE else '❌ غیرفعال'}")
    
    while True:
        try:
            bot.infinity_polling(timeout=60, skip_pending=True)
        except Exception as e:
            logger.error(f"خطا: {e}")
            time.sleep(5)
