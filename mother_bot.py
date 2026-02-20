#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر فوق‌پیشرفته - نسخه کامل با بخش‌های سرور کامنت شده
"""

import asyncio
import aiohttp
import aio_pika
import asyncpg
import aioredis
import uvloop
import docker
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
import signal
import shutil
import psutil
import re
import zipfile
import tarfile
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import logging
import traceback
from logging.handlers import RotatingFileHandler
import aiofiles
import magic
import redis
import pika
import minio
from minio import Minio
from minio.error import S3Error

# ==================== تنظیمات uvloop برای سرعت بالا ====================
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# ==================== تنظیمات پایه ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGS_DIR = os.path.join(BASE_DIR, "logs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

# ==================== توکن ربات مادر ====================
BOT_TOKEN = os.getenv('BOT_TOKEN', '8541672444:AAF4PBn7-XqiXUgaK0arVajyZfcMWqbxSJ0')
bot = telebot.TeleBot(BOT_TOKEN)
bot.delete_webhook()

# ==================== لاگینگ حرفه‌ای ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(
            os.path.join(LOGS_DIR, 'mother_bot.log'),
            maxBytes=10485760,  # 10MB
            backupCount=30
        ),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== تنظیمات اتصال به سرویس‌ها ====================
# این بخش‌ها مربوط به سرورهای خارجی هستند - فعلاً کامنت شده‌اند
"""
# PostgreSQL
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'postgres'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'admin'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'bot_empire'),
    'min_size': int(os.getenv('DB_POOL_MIN', 10)),
    'max_size': int(os.getenv('DB_POOL_MAX', 100)),
    'command_timeout': 60,
    'max_queries': 50000,
    'max_inactive_connection_lifetime': 300
}

# Redis
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'redis'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'password': os.getenv('REDIS_PASS', ''),
    'db': int(os.getenv('REDIS_DB', 0)),
    'max_connections': int(os.getenv('REDIS_MAX_CONN', 1000)),
    'decode_responses': True,
    'socket_keepalive': True,
    'socket_timeout': 5,
    'retry_on_timeout': True
}

# RabbitMQ
RABBITMQ_CONFIG = {
    'host': os.getenv('RABBITMQ_HOST', 'rabbitmq'),
    'port': int(os.getenv('RABBITMQ_PORT', 5672)),
    'login': os.getenv('RABBITMQ_USER', 'admin'),
    'password': os.getenv('RABBITMQ_PASS', ''),
    'virtual_host': '/',
    'connection_attempts': 10,
    'retry_delay': 5
}

# MinIO (S3 Compatible Storage)
MINIO_CONFIG = {
    'endpoint': os.getenv('MINIO_HOST', 'minio:9000'),
    'access_key': os.getenv('MINIO_ACCESS_KEY', 'admin'),
    'secret_key': os.getenv('MINIO_SECRET_KEY', ''),
    'secure': False,
    'bucket_name': os.getenv('MINIO_BUCKET', 'bot-files')
}

# Docker
DOCKER_CONFIG = {
    'base_url': os.getenv('DOCKER_HOST', 'unix://var/run/docker.sock'),
    'timeout': 120,
    'max_pool_size': 100
}
"""

# ==================== دیتابیس SQLite (جایگزین PostgreSQL) ====================
DB_PATH = os.path.join(BASE_DIR, 'mother_bot.db')

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
            language TEXT DEFAULT 'fa',
            balance INTEGER DEFAULT 0,
            plan TEXT DEFAULT 'free',
            bots_count INTEGER DEFAULT 0,
            settings TEXT DEFAULT '{}',
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
            description TEXT,
            status TEXT DEFAULT 'stopped',
            file_path TEXT,
            cpu_usage REAL DEFAULT 0,
            memory_usage REAL DEFAULT 0,
            requests_count INTEGER DEFAULT 0,
            errors_count INTEGER DEFAULT 0,
            last_error TEXT,
            settings TEXT DEFAULT '{}',
            created_at TIMESTAMP,
            last_active TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS files (
            id TEXT PRIMARY KEY,
            bot_id TEXT,
            name TEXT,
            path TEXT,
            size INTEGER,
            hash TEXT,
            uploaded_at TIMESTAMP,
            FOREIGN KEY(bot_id) REFERENCES bots(id)
        )
    ''')
    
    conn.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    
    conn.commit()

# ==================== دیتا کلاس‌ها ====================

@dataclass
class User:
    """مدل کاربر"""
    id: int
    username: str
    first_name: str
    last_name: Optional[str]
    language: str
    balance: float
    plan: str
    bots_count: int
    created_at: datetime
    last_active: datetime
    settings: Dict[str, Any]

@dataclass
class UserBot:
    """مدل ربات کاربر"""
    id: str
    user_id: int
    token: str
    name: str
    username: str
    description: str
    status: str
    file_path: Optional[str]
    cpu_usage: float
    memory_usage: float
    requests_count: int
    errors_count: int
    last_error: Optional[str]
    created_at: datetime
    last_active: datetime
    settings: Dict[str, Any]

@dataclass
class File:
    """مدل فایل"""
    id: str
    bot_id: str
    name: str
    path: str
    size: int
    hash: str
    uploaded_at: datetime

# ==================== توابع کمکی دیتابیس ====================

def get_user(user_id: int) -> Optional[User]:
    with get_db() as conn:
        row = conn.execute(
            'SELECT * FROM users WHERE user_id = ?',
            (user_id,)
        ).fetchone()
        if row:
            data = dict(row)
            data['settings'] = json.loads(data['settings']) if data['settings'] else {}
            return User(**data)
        return None

def create_user(user_id: int, username: str, first_name: str, last_name: Optional[str] = None) -> User:
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
        
        row = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()
        data = dict(row)
        data['settings'] = json.loads(data['settings']) if data['settings'] else {}
        return User(**data)

def create_bot(bot: UserBot) -> bool:
    with get_db() as conn:
        try:
            conn.execute('''
                INSERT INTO bots (
                    id, user_id, token, name, username, description,
                    status, file_path, settings, created_at, last_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (bot.id, bot.user_id, bot.token, bot.name, bot.username,
                  bot.description, bot.status, bot.file_path,
                  json.dumps(bot.settings), bot.created_at.isoformat(), bot.last_active.isoformat()))
            
            conn.execute('''
                UPDATE users SET bots_count = bots_count + 1, last_active = ?
                WHERE user_id = ?
            ''', (datetime.now().isoformat(), bot.user_id))
            
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create bot: {e}")
            return False

def update_bot(bot_id: str, **kwargs) -> bool:
    with get_db() as conn:
        try:
            fields = []
            values = []
            for key, value in kwargs.items():
                fields.append(f"{key} = ?")
                values.append(value)
            values.append(bot_id)
            
            query = f"UPDATE bots SET {', '.join(fields)}, last_active = ? WHERE id = ?"
            conn.execute(query, (*values, datetime.now().isoformat(), bot_id))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update bot {bot_id}: {e}")
            return False

def get_bot(bot_id: str) -> Optional[UserBot]:
    with get_db() as conn:
        row = conn.execute('SELECT * FROM bots WHERE id = ?', (bot_id,)).fetchone()
        if row:
            data = dict(row)
            data['settings'] = json.loads(data['settings']) if data['settings'] else {}
            data['created_at'] = datetime.fromisoformat(data['created_at'])
            data['last_active'] = datetime.fromisoformat(data['last_active'])
            return UserBot(**data)
        return None

def get_user_bots(user_id: int, limit: int = 10) -> List[UserBot]:
    with get_db() as conn:
        rows = conn.execute('''
            SELECT * FROM bots WHERE user_id = ?
            ORDER BY created_at DESC LIMIT ?
        ''', (user_id, limit)).fetchall()
        
        bots = []
        for row in rows:
            data = dict(row)
            data['settings'] = json.loads(data['settings']) if data['settings'] else {}
            data['created_at'] = datetime.fromisoformat(data['created_at'])
            data['last_active'] = datetime.fromisoformat(data['last_active'])
            bots.append(UserBot(**data))
        return bots

def save_file(file: File) -> bool:
    with get_db() as conn:
        try:
            conn.execute('''
                INSERT INTO files (id, bot_id, name, path, size, hash, uploaded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (file.id, file.bot_id, file.name, file.path, file.size,
                  file.hash, file.uploaded_at.isoformat()))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save file: {e}")
            return False

# ==================== کلاس‌های مدیریت سرور (کامنت شده) ====================
"""
class DatabaseManager:
    # مدیریت اتصال به PostgreSQL
    ...

class RedisManager:
    # مدیریت کش با Redis
    ...

class RabbitMQManager:
    # مدیریت صف پیام با RabbitMQ
    ...

class MinIOManager:
    # مدیریت ذخیره‌سازی فایل با MinIO
    ...

class DockerManager:
    # مدیریت کانتینرهای Docker
    ...
"""

# ==================== کلاس اصلی ربات مادر ====================

class MotherBot:
    """ربات مادر فوق‌پیشرفته - نسخه بدون سرور"""
    
    def __init__(self):
        self.bot = bot
        self.running = True
        self.start_time = datetime.now()
        self.stats = {
            'total_requests': 0,
            'total_bots': 0,
            'total_users': 0,
            'active_bots': 0
        }
        
        # Thread pool برای پردازش موازی
        self.executor = ThreadPoolExecutor(max_workers=10)
        
        logger.info("🤖 MotherBot instance created")
    
    async def initialize(self):
        """راه‌اندازی ربات"""
        try:
            # آپدیت آمار اولیه
            with get_db() as conn:
                self.stats['total_users'] = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
                self.stats['total_bots'] = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
                self.stats['active_bots'] = conn.execute(
                    'SELECT COUNT(*) FROM bots WHERE status = ?', ('running',)
                ).fetchone()[0]
            
            # شروع تسک‌های پس‌زمینه
            asyncio.create_task(self._update_stats())
            
            logger.info("✅ MotherBot initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            raise
    
    async def _update_stats(self):
        """به‌روزرسانی آمار"""
        while self.running:
            try:
                with get_db() as conn:
                    self.stats['total_users'] = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
                    self.stats['total_bots'] = conn.execute('SELECT COUNT(*) FROM bots').fetchone()[0]
                    self.stats['active_bots'] = conn.execute(
                        'SELECT COUNT(*) FROM bots WHERE status = ?', ('running',)
                    ).fetchone()[0]
                
                await asyncio.sleep(60)  # هر دقیقه
                
            except Exception as e:
                logger.error(f"Error updating stats: {e}")
                await asyncio.sleep(10)
    
    # ==================== هندلرهای تلگرام ====================
    
    def setup_handlers(self):
        """تنظیم هندلرهای تلگرام"""
        
        @self.bot.message_handler(commands=['start'])
        def cmd_start(message):
            asyncio.create_task(self._handle_start(message))
        
        @self.bot.message_handler(commands=['help'])
        def cmd_help(message):
            asyncio.create_task(self._handle_help(message))
        
        @self.bot.message_handler(commands=['stats'])
        def cmd_stats(message):
            asyncio.create_task(self._handle_stats(message))
        
        @self.bot.message_handler(commands=['bots'])
        def cmd_bots(message):
            asyncio.create_task(self._handle_bots(message))
        
        @self.bot.message_handler(commands=['balance'])
        def cmd_balance(message):
            asyncio.create_task(self._handle_balance(message))
        
        @self.bot.message_handler(content_types=['document'])
        def handle_document(message):
            asyncio.create_task(self._handle_document(message))
        
        @self.bot.message_handler(func=lambda m: True)
        def handle_text(message):
            asyncio.create_task(self._handle_text(message))
    
    async def _handle_start(self, message):
        """هندلر /start"""
        user_id = message.from_user.id
        username = message.from_user.username or ""
        first_name = message.from_user.first_name or ""
        last_name = message.from_user.last_name or ""
        
        # ایجاد کاربر در دیتابیس
        user = create_user(user_id, username, first_name, last_name)
        
        # ارسال منو
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
        markup.add(
            types.KeyboardButton('🤖 ساخت ربات جدید'),
            types.KeyboardButton('📋 ربات‌های من'),
            types.KeyboardButton('💰 کیف پول'),
            types.KeyboardButton('📊 آمار'),
            types.KeyboardButton('📚 راهنما'),
            types.KeyboardButton('📞 پشتیبانی')
        )
        
        await self._send_message(
            chat_id=message.chat.id,
            text=f"🚀 **به ربات مادر خوش آمدید {first_name}!**\n\n"
                 f"👤 کاربر: {user_id}\n"
                 f"💰 موجودی: {user.balance:,} تومان\n"
                 f"🤖 ربات‌ها: {user.bots_count}\n\n"
                 f"📤 فایل خود را آپلود کنید تا رباتتان ساخته شود.",
            reply_markup=markup
        )
        
        self.stats['total_requests'] += 1
    
    async def _handle_help(self, message):
        """هندلر /help"""
        help_text = (
            "📚 **راهنمای استفاده**\n\n"
            "**🤖 ساخت ربات:**\n"
            "• فایل `.py` خود را آپلود کنید\n"
            "• فایل‌های فشرده `.zip` هم قبول میشه\n"
            "• توکن باید داخل کد باشه\n\n"
            "**📋 مدیریت:**\n"
            "• /bots - لیست ربات‌های شما\n"
            "• /balance - موجودی کیف پول\n"
            "• /stats - آمار کلی\n\n"
            "**💳 خرید:**\n"
            "• قالب آماده: ۵۰,۰۰۰ تومان\n"
            "• فضای بیشتر: ۱۰۰,۰۰۰ تومان\n"
            "• پشتیبانی VIP: ۲۰۰,۰۰۰ تومان\n\n"
            "**📞 پشتیبانی:**\n"
            "@support_bot"
        )
        
        await self._send_message(message.chat.id, help_text)
        self.stats['total_requests'] += 1
    
    async def _handle_stats(self, message):
        """هندلر /stats"""
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        
        text = f"📊 **آمار ربات مادر**\n\n"
        text += f"⏱ آپتایم: {hours:.1f} ساعت\n"
        text += f"👥 کاربران: {self.stats['total_users']:,}\n"
        text += f"🤖 ربات‌ها: {self.stats['total_bots']:,}\n"
        text += f"🟢 فعال: {self.stats['active_bots']:,}\n"
        text += f"📨 درخواست‌ها: {self.stats['total_requests']:,}\n"
        text += f"⚡ وضعیت: 🟢 عالی"
        
        await self._send_message(message.chat.id, text)
        self.stats['total_requests'] += 1
    
    async def _handle_bots(self, message):
        """هندلر /bots"""
        user_id = message.from_user.id
        
        bots = get_user_bots(user_id)
        
        if not bots:
            await self._send_message(
                message.chat.id,
                "📋 شما هنوز رباتی نساخته‌اید!"
            )
            return
        
        text = "📋 **ربات‌های شما:**\n\n"
        for bot in bots[:5]:
            emoji = "🟢" if bot.status == 'running' else "🔴"
            text += f"{emoji} **{bot.name}**\n"
            text += f"   🔗 https://t.me/{bot.username}\n"
            text += f"   🆔 {bot.id}\n"
            text += f"   📊 CPU: {bot.cpu_usage:.1f}% | RAM: {bot.memory_usage:.1f}MB\n"
            text += f"   📅 {bot.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
        
        await self._send_message(message.chat.id, text)
        self.stats['total_requests'] += 1
    
    async def _handle_balance(self, message):
        """هندلر /balance"""
        user_id = message.from_user.id
        
        user = get_user(user_id)
        
        text = f"💰 **کیف پول شما**\n\n"
        text += f"موجودی: {user.balance:,} تومان\n"
        text += f"پلن: {user.plan}\n"
        text += f"ربات‌ها: {user.bots_count}\n\n"
        text += f"**قیمت‌ها:**\n"
        text += f"• هر ربات: ۵۰,۰۰۰ تومان\n"
        text += f"• فضای ۱ گیگ: ۱۰,۰۰۰ تومان\n"
        text += f"• پشتیبانی VIP: ۲۰۰,۰۰۰ تومان"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="charge"))
        
        await self._send_message(message.chat.id, text, reply_markup=markup)
        self.stats['total_requests'] += 1
    
    async def _handle_document(self, message):
        """هندلر آپلود فایل"""
        user_id = message.from_user.id
        file_name = message.document.file_name
        
        if not (file_name.endswith('.py') or file_name.endswith('.zip')):
            await self._send_message(
                message.chat.id,
                "❌ فقط فایل‌های `.py` یا `.zip` مجاز هستند!"
            )
            return
        
        if message.document.file_size > 50 * 1024 * 1024:
            await self._send_message(
                message.chat.id,
                "❌ حجم فایل نباید بیشتر از ۵۰ مگابایت باشد!"
            )
            return
        
        status_msg = await self._send_message(
            message.chat.id,
            "🔄 در حال پردازش فایل..."
        )
        
        try:
            # دانلود فایل
            file_info = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: bot.get_file(message.document.file_id)
            )
            downloaded_file = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: bot.download_file(file_info.file_path)
            )
            
            # ایجاد پوشه کاربر
            user_dir = os.path.join(TEMP_DIR, str(user_id))
            os.makedirs(user_dir, exist_ok=True)
            
            # ذخیره فایل
            timestamp = int(time.time())
            file_path = os.path.join(user_dir, f"{timestamp}_{file_name}")
            
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
            
            files_content = {}
            
            if file_name.endswith('.zip'):
                # استخراج فایل‌های zip
                extract_dir = os.path.join(user_dir, f"extract_{timestamp}")
                os.makedirs(extract_dir, exist_ok=True)
                
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)
                
                for root, _, files in os.walk(extract_dir):
                    for f in files:
                        if f.endswith('.py'):
                            file_path_full = os.path.join(root, f)
                            with open(file_path_full, 'r', encoding='utf-8') as fh:
                                files_content[f] = fh.read()
                
                shutil.rmtree(extract_dir)
            
            else:  # فایل .py
                with open(file_path, 'r', encoding='utf-8') as f:
                    files_content[file_name] = f.read()
            
            if not files_content:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ هیچ فایل پایتونی پیدا نشد!"
                )
                return
            
            # پیدا کردن فایل اصلی
            main_file = list(files_content.keys())[0]
            main_code = files_content[main_file]
            
            # اعتبارسنجی کد
            try:
                compile(main_code, '<string>', 'exec')
            except SyntaxError as e:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    f"❌ خطای نحوی در کد:\n```\n{str(e)}\n```"
                )
                return
            
            # استخراج توکن
            token_match = re.search(
                r'token\s*=\s*["\']([^"\']+)["\']',
                main_code,
                re.IGNORECASE
            )
            
            if not token_match:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ توکن در کد پیدا نشد!\nمثال: TOKEN = '123456:ABCdef'"
                )
                return
            
            token = token_match.group(1)
            
            # تست توکن
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"https://api.telegram.org/bot{token}/getMe") as resp:
                        if resp.status != 200:
                            await self._edit_message(
                                status_msg.chat.id,
                                status_msg.message_id,
                                "❌ توکن معتبر نیست!"
                            )
                            return
                        
                        bot_info = await resp.json()
                        bot_name = bot_info['result']['first_name']
                        bot_username = bot_info['result']['username']
                        
            except Exception as e:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    f"❌ خطا در بررسی توکن: {str(e)}"
                )
                return
            
            # آیدی یکتا برای ربات
            bot_id = hashlib.md5(f"{user_id}_{token}_{time.time()}".encode()).hexdigest()[:10]
            
            # ایجاد ربات جدید در دیتابیس
            new_bot = UserBot(
                id=bot_id,
                user_id=user_id,
                token=token,
                name=bot_name,
                username=bot_username,
                description="",
                status='running',
                file_path=file_path,
                cpu_usage=0,
                memory_usage=0,
                requests_count=0,
                errors_count=0,
                last_error=None,
                created_at=datetime.now(),
                last_active=datetime.now(),
                settings={}
            )
            
            if create_bot(new_bot):
                self.stats['total_bots'] += 1
                self.stats['active_bots'] += 1
                
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    f"✅ **ربات با موفقیت ساخته شد!** 🎉\n\n"
                    f"🤖 نام: {bot_name}\n"
                    f"🔗 لینک: https://t.me/{bot_username}\n"
                    f"🆔 آیدی: {bot_id}\n"
                    f"📦 فایل‌ها: {len(files_content)}\n"
                    f"🔄 وضعیت: در حال اجرا\n\n"
                    f"💡 از /bots برای مدیریت استفاده کنید."
                )
            else:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ خطا در ذخیره‌سازی ربات!"
                )
            
            self.stats['total_requests'] += 1
            
        except Exception as e:
            logger.error(f"Error: {e}\n{traceback.format_exc()}")
            await self._edit_message(
                status_msg.chat.id,
                status_msg.message_id,
                f"❌ خطا: {str(e)}"
            )
    
    async def _handle_text(self, message):
        """هندلر متن"""
        text = message.text
        
        if text == '🤖 ساخت ربات جدید':
            await self._send_message(
                message.chat.id,
                "📤 **فایل خود را ارسال کنید**\n\n"
                "✅ فایل `.py` یا `.zip` بفرستید.\n"
                "✅ توکن باید داخل کد باشه.\n"
                "✅ حجم فایل تا ۵۰ مگابایت."
            )
        
        elif text == '📋 ربات‌های من':
            await self._handle_bots(message)
        
        elif text == '💰 کیف پول':
            await self._handle_balance(message)
        
        elif text == '📊 آمار':
            await self._handle_stats(message)
        
        elif text == '📚 راهنما':
            await self._handle_help(message)
        
        elif text == '📞 پشتیبانی':
            await self._send_message(
                message.chat.id,
                "📞 **پشتیبانی**\n\n"
                "برای ارتباط با پشتیبانی:\n"
                "• @support_bot\n"
                "• support@example.com\n"
                "• ۲۴ ساعته پاسخگو هستیم"
            )
        
        self.stats['total_requests'] += 1
    
    async def _send_message(self, chat_id, text, **kwargs):
        """ارسال پیام با مدیریت خطا"""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.bot.send_message(
                    chat_id,
                    text,
                    parse_mode='Markdown',
                    **kwargs
                )
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            return None
    
    async def _edit_message(self, chat_id, message_id, text, **kwargs):
        """ویرایش پیام با مدیریت خطا"""
        try:
            return await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.bot.edit_message_text(
                    text,
                    chat_id,
                    message_id,
                    parse_mode='Markdown',
                    **kwargs
                )
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            return None
    
    async def run(self):
        """اجرای ربات"""
        try:
            # راه‌اندازی
            await self.initialize()
            
            # تنظیم هندلرها
            self.setup_handlers()
            
            logger.info("🚀 MotherBot started successfully")
            
            # اجرای ربات
            while self.running:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: self.bot.infinity_polling(timeout=60)
                    )
                except Exception as e:
                    logger.error(f"Bot polling error: {e}")
                    await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Fatal error: {e}")
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """پاک‌سازی منابع"""
        logger.info("🔄 Cleaning up resources...")
        
        self.running = False
        self.executor.shutdown()
        
        logger.info("✅ Cleanup completed")

# ==================== اجرای اصلی ====================

async def main():
    """تابع اصلی"""
    mother_bot = MotherBot()
    
    try:
        await mother_bot.run()
    except KeyboardInterrupt:
        logger.info("🛑 Received shutdown signal")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        await mother_bot.cleanup()

if __name__ == "__main__":
    asyncio.run(main())
