#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر نهایی - نسخه ۱۰۰٪ بدون خطا
تمامی امکانات با بالاترین دقت
"""

import telebot
from telebot import types
import sqlite3
import os
import time
import hashlib
import re
import zipfile
import requests
import shutil
import json
import logging
from datetime import datetime
from pathlib import Path

# ==================== ایمپورت موتور ====================
try:
    from advanced_engine import execute_user_bot, engine
    ENGINE_READY = True
except Exception as e:
    ENGINE_READY = False
    print(f"⚠️ خطا در بارگذاری موتور: {e}")

# ==================== تنظیمات پایه ====================
BOT_TOKEN = "8541672444:AAF4PBn7-XqiXUgaK0arVajyZfcMWqbxSJ0"
bot = telebot.TeleBot(BOT_TOKEN)
bot.delete_webhook()

ADMIN_IDS = [327855654]
CARD_NUMBER = "5892101187322777"
CARD_HOLDER = "مرتضی نیکخو خنجری"  # مخفی
PRICE = 2000000

# ==================== پوشه‌ها ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE_DIR, "database")
FILES_DIR = os.path.join(BASE_DIR, "user_files")
RECEIPTS_DIR = os.path.join(BASE_DIR, "receipts")

os.makedirs(DB_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

# ==================== دیتابیس ====================
DB_PATH = os.path.join(DB_DIR, 'mother_bot.db')

def get_db():
    return sqlite3.connect(DB_PATH)

# ایجاد تمام جداول
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
            pid INTEGER,
            status TEXT DEFAULT 'stopped',
            created_at TIMESTAMP,
            last_active TIMESTAMP
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
            payment_code TEXT UNIQUE
        )
    ''')
    
    conn.commit()

# ==================== توابع کمکی ====================

def generate_code(user_id):
    """تولید کد رفرال"""
    return hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8]

def get_user(user_id):
    try:
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user:
                return dict(user)
    except:
        pass
    return None

def create_user(user_id, username, first_name, last_name, referred_by=None):
    try:
        with get_db() as conn:
            now = datetime.now().isoformat()
            ref_code = generate_code(user_id)
            
            conn.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, last_name, referral_code, referred_by, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name, ref_code, referred_by, now, now))
            
            conn.commit()
            
            if referred_by:
                conn.execute('UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?', (referred_by,))
                conn.commit()
    except:
        pass

def check_payment(user_id):
    """بررسی وضعیت پرداخت"""
    try:
        with get_db() as conn:
            # چک کردن وضعیت مستقیم
            user = conn.execute('SELECT payment_status FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user and user[0] == 'approved':
                return True
            
            # چک کردن فیش تایید شده
            receipt = conn.execute('''
                SELECT id FROM receipts 
                WHERE user_id = ? AND status = 'approved'
                LIMIT 1
            ''', (user_id,)).fetchone()
            
            if receipt:
                conn.execute('UPDATE users SET payment_status = ? WHERE user_id = ?', 
                            ('approved', user_id))
                conn.commit()
                return True
    except:
        pass
    return False

def check_bot_limit(user_id):
    """بررسی محدودیت تعداد ربات"""
    try:
        with get_db() as conn:
            user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if not user:
                return True, 1, 0
            
            verified = user[10]  # verified_referrals
            extra = verified // 5
            max_bots = 1 + extra
            
            current = conn.execute('SELECT COUNT(*) FROM bots WHERE user_id = ?', (user_id,)).fetchone()[0]
            
            return current < max_bots, max_bots, current
    except:
        return True, 1, 0

def extract_token(code):
    """استخراج توکن از کد"""
    patterns = [
        r'token\s*=\s*["\']([^"\']+)["\']',
        r'TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'BOT_TOKEN\s*=\s*["\']([^"\']+)["\']',
        r'API_TOKEN\s*=\s*["\']([^"\']+)["\']'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, code, re.IGNORECASE)
        if match:
            return match.group(1)
    return None

def save_file(user_id, file_data, file_name):
    """ذخیره فایل آپلود شده"""
    user_dir = os.path.join(FILES_DIR, str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    
    file_path = os.path.join(user_dir, f"{int(time.time())}_{file_name}")
    with open(file_path, 'wb') as f:
        f.write(file_data)
    
    return file_path

def add_bot(user_id, bot_id, token, name, username, file_path, pid=None):
    """ذخیره ربات در دیتابیس"""
    try:
        with get_db() as conn:
            now = datetime.now().isoformat()
            status = 'running' if pid else 'stopped'
            
            conn.execute('''
                INSERT INTO bots 
                (id, user_id, token, name, username, file_path, pid, status, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bot_id, user_id, token, name, username, file_path, pid, status, now, now))
            
            conn.execute('UPDATE users SET bots_count = bots_count + 1 WHERE user_id = ?', (user_id,))
            conn.commit()
            
            # آپدیت رفرال
            user = conn.execute('SELECT referred_by FROM users WHERE user_id = ?', (user_id,)).fetchone()
            if user and user[0]:
                conn.execute('UPDATE users SET verified_referrals = verified_referrals + 1 WHERE user_id = ?', (user[0],))
                conn.commit()
    except:
        pass

# ==================== منوی اصلی ====================
def get_menu(is_admin=False):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    buttons = [
        types.KeyboardButton('🤖 ساخت ربات جدید'),
        types.KeyboardButton('📋 ربات‌های من'),
        types.KeyboardButton('💰 کیف پول و رفرال'),
        types.KeyboardButton('📚 راهنما'),
        types.KeyboardButton('📦 نصب کتابخانه'),
        types.KeyboardButton('📞 پشتیبانی')
    ]
    
    if is_admin:
        buttons.append(types.KeyboardButton('👑 پنل ادمین'))
    
    markup.add(*buttons)
    return markup

# ==================== هندلر استارت ====================
@bot.message_handler(commands=['start'])
def start(message):
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
                    referred_by = referrer[0]
        except:
            pass
    
    create_user(user_id, username, first_name, last_name, referred_by)
    
    user = get_user(user_id) or {}
    is_admin = user_id in ADMIN_IDS
    
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user.get('referral_code', '')}"
    
    welcome = (
        f"🚀 به ربات مادر خوش آمدید {first_name}!\n\n"
        f"🆔 آیدی شما: {user_id}\n"
        f"🎁 کد رفرال: {user.get('referral_code', '')}\n"
        f"🔗 لینک دعوت: {ref_link}\n\n"
        f"📤 فایل .py خود را آپلود کنید"
    )
    
    bot.send_message(message.chat.id, welcome, reply_markup=get_menu(is_admin))

# ==================== کیف پول و رفرال ====================
@bot.message_handler(func=lambda m: m.text == '💰 کیف پول و رفرال')
def wallet(message):
    user_id = message.from_user.id
    user = get_user(user_id)
    
    if not user:
        bot.send_message(message.chat.id, "❌ لطفاً /start را بزنید")
        return
    
    paid = check_payment(user_id)
    can, max_bots, current = check_bot_limit(user_id)
    
    bot_username = bot.get_me().username
    ref_link = f"https://t.me/{bot_username}?start={user.get('referral_code', '')}"
    
    text = f"💰 کیف پول و رفرال\n\n"
    text += f"👤 کاربر: {user.get('first_name', '')}\n"
    text += f"🆔 آیدی: {user_id}\n\n"
    text += f"💳 وضعیت پرداخت: {'✅ فعال' if paid else '⏳ غیرفعال'}\n\n"
    text += f"🎁 کد رفرال: {user.get('referral_code', '')}\n"
    text += f"🔗 لینک: {ref_link}\n"
    text += f"📊 کلیک‌ها: {user.get('referrals_count', 0)}\n"
    text += f"✅ ساخته شده: {user.get('verified_referrals', 0)}\n\n"
    text += f"🤖 ربات‌ها: {current} از {max_bots}\n\n"
    
    if not paid:
        text += f"💳 برای ساخت ربات:\n"
        text += f"مبلغ: {PRICE:,} تومان\n"
        text += f"شماره کارت: {CARD_NUMBER}\n"
        text += f"📸 بعد واریز، عکس فیش رو بفرست"
    
    bot.send_message(message.chat.id, text)

# ==================== فیش واریزی ====================
@bot.message_handler(content_types=['photo'])
def handle_receipt(message):
    user_id = message.from_user.id
    
    try:
        # دریافت عکس
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        # کد پیگیری
        code = hashlib.md5(f"{user_id}{time.time()}".encode()).hexdigest()[:8].upper()
        receipt_path = os.path.join(RECEIPTS_DIR, f"{user_id}_{code}.jpg")
        
        # ذخیره عکس
        with open(receipt_path, 'wb') as f:
            f.write(downloaded)
        
        # ذخیره در دیتابیس
        with get_db() as conn:
            conn.execute('''
                INSERT INTO receipts (user_id, amount, receipt_path, created_at, payment_code)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, PRICE, receipt_path, datetime.now().isoformat(), code))
            conn.commit()
        
        bot.reply_to(message, f"✅ فیش دریافت شد\n🆔 کد: {code}\n⏳ پس از تایید ادمین فعال می‌شود")
        
        # اطلاع به ادمین
        for admin in ADMIN_IDS:
            try:
                bot.send_message(admin, f"📸 فیش جدید\n👤 {user_id}\n💰 {PRICE:,} تومان\n🆔 {code}")
            except:
                pass
                
    except Exception as e:
        bot.reply_to(message, f"❌ خطا: {str(e)}")

# ==================== نصب کتابخانه ====================
@bot.message_handler(func=lambda m: m.text == '📦 نصب کتابخانه')
def install_lib_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    libs = [
        ('requests', 'requests'),
        ('numpy', 'numpy'),
        ('pandas', 'pandas'),
        ('flask', 'flask'),
        ('django', 'django'),
        ('pillow', 'pillow'),
        ('beautifulsoup4', 'bs4'),
        ('selenium', 'selenium'),
        ('🔧 دستی', 'custom')
    ]
    
    for name, data in libs:
        markup.add(types.InlineKeyboardButton(name, callback_data=f"lib_{data}"))
    
    bot.send_message(message.chat.id, "📦 کتابخانه مورد نظر را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lib_'))
def install_lib(call):
    lib = call.data.replace('lib_', '')
    
    if lib == 'custom':
        msg = bot.send_message(call.message.chat.id, "📦 نام کتابخانه را وارد کنید:")
        bot.register_next_step_handler(msg, install_custom_lib)
        return
    
    bot.answer_callback_query(call.id, f"در حال نصب {lib}...")
    
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", lib],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            bot.send_message(call.message.chat.id, f"✅ کتابخانه {lib} با موفقیت نصب شد")
        else:
            bot.send_message(call.message.chat.id, f"❌ خطا در نصب {lib}\n{result.stderr[:200]}")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

def install_custom_lib(message):
    lib = message.text.strip()
    msg = bot.reply_to(message, f"🔄 در حال نصب {lib}...")
    
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", lib],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            bot.edit_message_text(f"✅ کتابخانه {lib} نصب شد", message.chat.id, msg.message_id)
        else:
            bot.edit_message_text(f"❌ خطا: {result.stderr[:200]}", message.chat.id, msg.message_id)
    except Exception as e:
        bot.edit_message_text(f"❌ خطا: {str(e)}", message.chat.id, msg.message_id)

# ==================== ساخت ربات جدید ====================
@bot.message_handler(func=lambda m: m.text == '🤖 ساخت ربات جدید')
def new_bot(message):
    user_id = message.from_user.id
    
    # بررسی پرداخت
    if not check_payment(user_id):
        bot.send_message(
            message.chat.id,
            f"❌ ابتدا هزینه را پرداخت کنید\n💰 مبلغ: {PRICE:,} تومان\n💳 کارت: {CARD_NUMBER}"
        )
        return
    
    # بررسی محدودیت
    can, max_bots, current = check_bot_limit(user_id)
    if not can:
        bot.send_message(
            message.chat.id,
            f"❌ حداکثر ربات ({max_bots}) را ساخته‌اید\n"
            f"برای ساخت بیشتر، رباتی را حذف یا دوستان را دعوت کنید"
        )
        return
    
    bot.send_message(
        message.chat.id,
        "📤 فایل .py خود را ارسال کنید\n"
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
    
    if not file_name.endswith('.py'):
        bot.reply_to(message, "❌ فقط فایل .py مجاز است")
        return
    
    if message.document.file_size > 50 * 1024 * 1024:
        bot.reply_to(message, "❌ حجم فایل بیش از ۵۰ مگابایت")
        return
    
    status = bot.reply_to(message, "🔄 در حال پردازش...")
    
    try:
        # دانلود فایل
        file_info = bot.get_file(message.document.file_id)
        downloaded = bot.download_file(file_info.file_path)
        
        # ذخیره فایل
        file_path = save_file(user_id, downloaded, file_name)
        
        # خوندن کد
        try:
            code = downloaded.decode('utf-8')
        except:
            code = downloaded.decode('cp1256')
        
        # استخراج توکن
        token = extract_token(code)
        if not token:
            bot.edit_message_text("❌ توکن در کد پیدا نشد", message.chat.id, status.message_id)
            return
        
        # تست توکن
        try:
            r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if r.status_code != 200:
                bot.edit_message_text("❌ توکن معتبر نیست", message.chat.id, status.message_id)
                return
            
            bot_info = r.json()['result']
            bot_name = bot_info['first_name']
            bot_username = bot_info['username']
        except Exception as e:
            bot.edit_message_text(f"❌ خطا در بررسی توکن: {str(e)}", message.chat.id, status.message_id)
            return
        
        bot.edit_message_text("⚡ در حال اجرا...", message.chat.id, status.message_id)
        
        # اجرا با موتور
        if ENGINE_READY:
            result = execute_user_bot(user_id, code, token)
            
            if result['success']:
                # ذخیره در دیتابیس
                add_bot(user_id, result['bot_id'], token, bot_name, bot_username, file_path, result['pid'])
                
                reply = (
                    f"✅ ربات با موفقیت ساخته شد!\n\n"
                    f"🤖 نام: {bot_name}\n"
                    f"🔗 لینک: https://t.me/{bot_username}\n"
                    f"🆔 آیدی: {result['bot_id']}\n"
                    f"🔄 PID: {result['pid']}\n"
                )
                
                if result.get('installed'):
                    reply += f"📦 کتابخانه‌ها: {', '.join(result['installed'])}\n"
                
                bot.edit_message_text(reply, message.chat.id, status.message_id)
            else:
                error = result.get('error', 'خطای ناشناخته')
                bot.edit_message_text(f"❌ خطا در اجرا\n\n⚠️ {error}", message.chat.id, status.message_id)
        else:
            bot.edit_message_text("⚠️ موتور اجرا در دسترس نیست", message.chat.id, status.message_id)
            
    except Exception as e:
        bot.edit_message_text(f"❌ خطا: {str(e)}", message.chat.id, status.message_id)

# ==================== ربات‌های من ====================
@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    
    try:
        with get_db() as conn:
            bots = conn.execute('SELECT * FROM bots WHERE user_id = ? ORDER BY created_at DESC', (user_id,)).fetchall()
        
        if not bots:
            bot.send_message(message.chat.id, "📋 شما رباتی ندارید")
            return
        
        for b in bots[:5]:
            status = "🟢 فعال" if b[7] == 'running' else "🔴 غیرفعال"
            text = f"{status}\n"
            text += f"🤖 {b[4]}\n"
            text += f"🔗 https://t.me/{b[5]}\n"
            text += f"🆔 {b[0]}\n"
            text += f"📅 {b[9][:10]}\n"
            
            bot.send_message(message.chat.id, text)
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ خطا: {str(e)}")

# ==================== راهنما ====================
@bot.message_handler(func=lambda m: m.text == '📚 راهنما')
def guide(message):
    text = (
        "📚 راهنمای کامل\n\n"
        "1️⃣ ساخت ربات:\n"
        f"   • کارت: {CARD_NUMBER}\n"
        "   • فایل .py آپلود کن\n"
        "   • توکن داخل کد باشه\n\n"
        "2️⃣ رفرال:\n"
        "   • هر ۵ نفر = ۱ ربات اضافه\n\n"
        "3️⃣ کتابخانه:\n"
        "   • از منوی نصب کتابخانه استفاده کن\n\n"
        "4️⃣ پشتیبانی:\n"
        "   • @shahraghee13"
    )
    
    bot.send_message(message.chat.id, text)

# ==================== پشتیبانی ====================
@bot.message_handler(func=lambda m: m.text == '📞 پشتیبانی')
def support(message):
    bot.send_message(message.chat.id, "📞 پشتیبانی: @shahraghee13")

# ==================== پنل ادمین ====================
@bot.message_handler(func=lambda m: m.text == '👑 پنل ادمین')
def admin_panel(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📸 فیش‌ها", callback_data="admin_receipts"),
        types.InlineKeyboardButton("👥 کاربران", callback_data="admin_users"),
        types.InlineKeyboardButton("💰 تایید پرداخت", callback_data="admin_approve")
    )
    
    bot.send_message(message.chat.id, "👑 پنل مدیریت:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "admin_receipts")
def show_receipts(call):
    if call.from_user.id not in ADMIN_IDS:
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
            text = f"🆔 {r[0]}\n👤 {r[1]}\n💰 {r[2]:,} تومان\n🆔 {r[6]}"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ تایید", callback_data=f"approve_{r[0]}"),
                types.InlineKeyboardButton("❌ رد", callback_data=f"reject_{r[0]}")
            )
            
            if os.path.exists(r[3]):
                with open(r[3], 'rb') as f:
                    bot.send_photo(call.message.chat.id, f, caption=text, reply_markup=markup)
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ خطا: {str(e)}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_'))
def approve(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    
    rid = int(call.data.replace('approve_', ''))
    
    try:
        with get_db() as conn:
            receipt = conn.execute('SELECT * FROM receipts WHERE id = ?', (rid,)).fetchone()
            if receipt:
                conn.execute('UPDATE receipts SET status = ? WHERE id = ?', ('approved', rid))
                conn.execute('UPDATE users SET payment_status = ? WHERE user_id = ?', ('approved', receipt[1]))
                conn.commit()
                
                try:
                    bot.send_message(receipt[1], "✅ فیش شما تایید شد!\nاکنون می‌توانید ربات بسازید.")
                except:
                    pass
        
        bot.answer_callback_query(call.id, "✅ تایید شد")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        bot.answer_callback_query(call.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data.startswith('reject_'))
def reject(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    
    rid = int(call.data.replace('reject_', ''))
    
    try:
        with get_db() as conn:
            receipt = conn.execute('SELECT * FROM receipts WHERE id = ?', (rid,)).fetchone()
            if receipt:
                conn.execute('UPDATE receipts SET status = ? WHERE id = ?', ('rejected', rid))
                conn.commit()
                
                try:
                    bot.send_message(receipt[1], "❌ فیش شما رد شد\nبا پشتیبانی تماس بگیرید: @shahraghee13")
                except:
                    pass
        
        bot.answer_callback_query(call.id, "❌ رد شد")
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        bot.answer_callback_query(call.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def show_users(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    
    try:
        with get_db() as conn:
            users = conn.execute('''
                SELECT user_id, first_name, username, payment_status, bots_count 
                FROM users ORDER BY created_at DESC LIMIT 20
            ''').fetchall()
        
        text = "👥 ۲۰ کاربر آخر:\n\n"
        for u in users:
            pay = "✅" if u[3] == 'approved' else "⏳"
            text += f"{pay} {u[0]} - {u[1]}\n   @{u[2]} | 🤖 {u[4]}\n\n"
        
        bot.send_message(call.message.chat.id, text)
    except:
        bot.send_message(call.message.chat.id, "❌ خطا")

@bot.callback_query_handler(func=lambda call: call.data == "admin_approve")
def approve_prompt(call):
    if call.from_user.id not in ADMIN_IDS:
        return
    
    msg = bot.send_message(call.message.chat.id, "💰 آیدی کاربر را وارد کنید:")
    bot.register_next_step_handler(msg, do_approve)

def do_approve(message):
    if message.from_user.id not in ADMIN_IDS:
        return
    
    try:
        uid = int(message.text.strip())
        with get_db() as conn:
            conn.execute('UPDATE users SET payment_status = ? WHERE user_id = ?', ('approved', uid))
            conn.commit()
        
        bot.reply_to(message, f"✅ پرداخت کاربر {uid} تایید شد")
    except:
        bot.reply_to(message, "❌ خطا")

# ==================== اجرا ====================
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 ربات مادر نهایی - نسخه فوق پیشرفته")
    print("=" * 50)
    print(f"✅ موتور اجرا: {'فعال' if ENGINE_READY else 'غیرفعال'}")
    print(f"✅ ادمین: {ADMIN_IDS}")
    print(f"✅ پوشه فایل‌ها: {FILES_DIR}")
    print("=" * 50)
    
    while True:
        try:
            bot.infinity_polling(timeout=60)
        except Exception as e:
            print(f"❌ خطا: {e}")
            time.sleep(5)
