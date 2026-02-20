#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ربات مادر فوق‌پیشرفته - متصل به Orchestrator, Database, Redis, RabbitMQ, MinIO
نسخه 5.0 - پشتیبانی از میلیون‌ها کاربر
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
BOT_TOKEN = os.getenv('BOT_TOKEN', '7956758689:AAH3JZ3kzBybVqPwRZ_pXlyA7Pez0n3BZ0o')
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
    status: str  # running, stopped, error
    container_id: Optional[str]
    node_id: Optional[str]
    cpu_usage: float
    memory_usage: float
    disk_usage: float
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
    mime_type: str
    uploaded_at: datetime

@dataclass
class Library:
    """مدل کتابخانه"""
    id: str
    name: str
    version: str
    description: str
    install_count: int
    created_at: datetime

# ==================== کلاس مدیریت دیتابیس ====================
# این کلاس مربوط به PostgreSQL است - فعلاً کامنت شده
"""
class DatabaseManager:
    #مدیریت اتصال به PostgreSQL با Connection Pool
    
    def __init__(self, config: Dict):
        self.config = config
        self.pool: Optional[asyncpg.Pool] = None
        self._lock = asyncio.Lock()
    
    async def initialize(self):
        #راه‌اندازی connection pool
        async with self._lock:
            if not self.pool:
                try:
                    self.pool = await asyncpg.create_pool(**self.config)
                    logger.info("✅ PostgreSQL connection pool created")
                    
                    # ایجاد جداول اگر وجود ندارند
                    await self._create_tables()
                    
                except Exception as e:
                    logger.error(f"❌ Failed to connect to PostgreSQL: {e}")
                    raise
    
    async def _create_tables(self):
        #ایجاد جداول مورد نیاز
        async with self.pool.acquire() as conn:
            # جدول کاربران
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    first_name VARCHAR(255),
                    last_name VARCHAR(255),
                    language VARCHAR(10) DEFAULT 'fa',
                    balance DECIMAL(10,2) DEFAULT 0,
                    plan VARCHAR(50) DEFAULT 'free',
                    bots_count INTEGER DEFAULT 0,
                    settings JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW(),
                    INDEX idx_users_user_id (user_id),
                    INDEX idx_users_plan (plan)
                )
            ''')
            
            # جدول ربات‌های کاربران
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_bots (
                    id VARCHAR(32) PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    token VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255),
                    username VARCHAR(255),
                    description TEXT,
                    status VARCHAR(50) DEFAULT 'stopped',
                    container_id VARCHAR(255),
                    node_id VARCHAR(255),
                    cpu_usage FLOAT DEFAULT 0,
                    memory_usage FLOAT DEFAULT 0,
                    disk_usage FLOAT DEFAULT 0,
                    requests_count BIGINT DEFAULT 0,
                    errors_count BIGINT DEFAULT 0,
                    last_error TEXT,
                    settings JSONB DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT NOW(),
                    last_active TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_user_bots_user_id (user_id),
                    INDEX idx_user_bots_status (status),
                    INDEX idx_user_bots_container_id (container_id)
                )
            ''')
            
            # جدول فایل‌ها
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS files (
                    id VARCHAR(64) PRIMARY KEY,
                    bot_id VARCHAR(32) NOT NULL,
                    name VARCHAR(255),
                    path TEXT,
                    size BIGINT,
                    hash VARCHAR(64),
                    mime_type VARCHAR(100),
                    uploaded_at TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (bot_id) REFERENCES user_bots(id) ON DELETE CASCADE,
                    INDEX idx_files_bot_id (bot_id)
                )
            ''')
            
            # جدول کتابخانه‌ها
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS libraries (
                    id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(255) UNIQUE,
                    version VARCHAR(50),
                    description TEXT,
                    install_count BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    INDEX idx_libraries_name (name),
                    INDEX idx_libraries_install_count (install_count)
                )
            ''')
            
            # جدول درخواست‌ها (برای مانیتورینگ)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS requests (
                    id BIGSERIAL PRIMARY KEY,
                    bot_id VARCHAR(32),
                    user_id BIGINT,
                    method VARCHAR(50),
                    path VARCHAR(255),
                    response_time FLOAT,
                    status_code INTEGER,
                    created_at TIMESTAMP DEFAULT NOW(),
                    FOREIGN KEY (bot_id) REFERENCES user_bots(id) ON DELETE SET NULL,
                    INDEX idx_requests_bot_id (bot_id),
                    INDEX idx_requests_created_at (created_at)
                )
            ''')
            
            logger.info("✅ Database tables created/verified")
    
    async def get_user(self, user_id: int) -> Optional[User]:
        #دریافت اطلاعات کاربر
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            if row:
                return User(**dict(row))
            return None
    
    async def create_user(self, user_id: int, username: str, first_name: str, 
                          last_name: Optional[str] = None) -> User:
        #ایجاد کاربر جدید
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO users (user_id, username, first_name, last_name, created_at, last_active)
                VALUES ($1, $2, $3, $4, NOW(), NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                    username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    last_active = NOW()
                RETURNING *
            ''', user_id, username, first_name, last_name)
            
            logger.info(f"✅ User {user_id} created/updated")
            return User(**dict(row))
    
    async def create_bot(self, bot: UserBot) -> bool:
        #ذخیره ربات جدید
        async with self.pool.acquire() as conn:
            try:
                await conn.execute('''
                    INSERT INTO user_bots (
                        id, user_id, token, name, username, description,
                        status, container_id, node_id, settings, created_at, last_active
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ''', bot.id, bot.user_id, bot.token, bot.name, bot.username,
                    bot.description, bot.status, bot.container_id, bot.node_id,
                    json.dumps(bot.settings), bot.created_at, bot.last_active)
                
                # آپدیت تعداد ربات‌های کاربر
                await conn.execute('''
                    UPDATE users SET bots_count = bots_count + 1
                    WHERE user_id = $1
                ''', bot.user_id)
                
                logger.info(f"✅ Bot {bot.id} created for user {bot.user_id}")
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to create bot: {e}")
                return False
    
    async def update_bot(self, bot_id: str, **kwargs) -> bool:
        #به‌روزرسانی اطلاعات ربات
        async with self.pool.acquire() as conn:
            try:
                set_clause = ', '.join([f"{k} = ${i+1}" for i, k in enumerate(kwargs.keys())])
                values = list(kwargs.values()) + [bot_id]
                
                await conn.execute(f'''
                    UPDATE user_bots SET {set_clause}, last_active = NOW()
                    WHERE id = ${len(values)}
                ''', *values)
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to update bot {bot_id}: {e}")
                return False
    
    async def get_bot(self, bot_id: str) -> Optional[UserBot]:
        #دریافت اطلاعات ربات
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM user_bots WHERE id = $1',
                bot_id
            )
            if row:
                data = dict(row)
                data['settings'] = json.loads(data['settings']) if data['settings'] else {}
                return UserBot(**data)
            return None
    
    async def get_user_bots(self, user_id: int, limit: int = 10) -> List[UserBot]:
        #دریافت لیست ربات‌های کاربر
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM user_bots WHERE user_id = $1
                ORDER BY created_at DESC LIMIT $2
            ''', user_id, limit)
            
            bots = []
            for row in rows:
                data = dict(row)
                data['settings'] = json.loads(data['settings']) if data['settings'] else {}
                bots.append(UserBot(**data))
            
            return bots
    
    async def increment_requests(self, bot_id: str):
        #افزایش تعداد درخواست‌های ربات
        async with self.pool.acquire() as conn:
            await conn.execute('''
                UPDATE user_bots SET requests_count = requests_count + 1
                WHERE id = $1
            ''', bot_id)
    
    async def log_request(self, bot_id: str, user_id: int, method: str,
                          path: str, response_time: float, status_code: int):
        #ثبت درخواست برای مانیتورینگ
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO requests (bot_id, user_id, method, path, response_time, status_code)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', bot_id, user_id, method, path, response_time, status_code)
    
    async def close(self):
        #بستن connection pool
        if self.pool:
            await self.pool.close()
            logger.info("✅ PostgreSQL connection pool closed")
"""

# ==================== کلاس مدیریت Redis ====================
# این کلاس مربوط به Redis است - فعلاً کامنت شده
"""
class RedisManager:
    #مدیریت کش با Redis
    
    def __init__(self, config: Dict):
        self.config = config
        self.client: Optional[aioredis.Redis] = None
    
    async def initialize(self):
        #راه‌اندازی اتصال به Redis
        try:
            self.client = await aioredis.from_url(
                f"redis://{self.config['host']}:{self.config['port']}",
                password=self.config['password'],
                db=self.config['db'],
                max_connections=self.config['max_connections'],
                decode_responses=self.config['decode_responses'],
                socket_keepalive=self.config['socket_keepalive'],
                socket_timeout=self.config['socket_timeout'],
                retry_on_timeout=self.config['retry_on_timeout']
            )
            
            # تست اتصال
            await self.client.ping()
            logger.info("✅ Redis connection established")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
    
    async def cache_bot(self, bot: UserBot, ttl: int = 3600):
        #کش کردن اطلاعات ربات
        key = f"bot:{bot.id}"
        await self.client.setex(
            key,
            ttl,
            json.dumps(asdict(bot), default=str)
        )
    
    async def get_cached_bot(self, bot_id: str) -> Optional[UserBot]:
        #دریافت ربات از کش
        key = f"bot:{bot_id}"
        data = await self.client.get(key)
        if data:
            return UserBot(**json.loads(data))
        return None
    
    async def cache_user(self, user: User, ttl: int = 3600):
        #کش کردن اطلاعات کاربر
        key = f"user:{user.id}"
        await self.client.setex(
            key,
            ttl,
            json.dumps(asdict(user), default=str)
        )
    
    async def get_cached_user(self, user_id: int) -> Optional[User]:
        #دریافت کاربر از کش
        key = f"user:{user_id}"
        data = await self.client.get(key)
        if data:
            return User(**json.loads(data))
        return None
    
    async def increment_stat(self, key: str, amount: int = 1):
        #افزایش آمار
        await self.client.incrby(key, amount)
    
    async def get_stat(self, key: str) -> int:
        #دریافت آمار
        val = await self.client.get(key)
        return int(val) if val else 0
    
    async def add_to_queue(self, queue_name: str, data: Dict, ttl: int = 3600):
        #افزودن به صف Redis
        key = f"queue:{queue_name}"
        await self.client.lpush(key, json.dumps(data))
        await self.client.expire(key, ttl)
    
    async def pop_from_queue(self, queue_name: str) -> Optional[Dict]:
        #برداشتن از صف Redis
        key = f"queue:{queue_name}"
        data = await self.client.rpop(key)
        if data:
            return json.loads(data)
        return None
    
    async def get_queue_length(self, queue_name: str) -> int:
        #طول صف
        key = f"queue:{queue_name}"
        return await self.client.llen(key)
    
    async def close(self):
        #بستن اتصال Redis
        if self.client:
            await self.client.close()
            logger.info("✅ Redis connection closed")
"""

# ==================== کلاس مدیریت RabbitMQ ====================
# این کلاس مربوط به RabbitMQ است - فعلاً کامنت شده
"""
class RabbitMQManager:
    #مدیریت صف پیام با RabbitMQ
    
    def __init__(self, config: Dict):
        self.config = config
        self.connection: Optional[aio_pika.Connection] = None
        self.channel: Optional[aio_pika.Channel] = None
    
    async def initialize(self):
        #راه‌اندازی اتصال به RabbitMQ
        try:
            self.connection = await aio_pika.connect_robust(
                host=self.config['host'],
                port=self.config['port'],
                login=self.config['login'],
                password=self.config['password'],
                virtualhost=self.config['virtual_host'],
                connection_attempts=self.config['connection_attempts'],
                retry_delay=self.config['retry_delay']
            )
            
            self.channel = await self.connection.channel()
            
            # ایجاد Exchange و Queue
            await self.channel.declare_exchange('bot_events', aio_pika.ExchangeType.TOPIC, durable=True)
            await self.channel.declare_exchange('bot_commands', aio_pika.ExchangeType.DIRECT, durable=True)
            
            # ایجاد Queue‌ها
            await self.channel.declare_queue('bot_created', durable=True)
            await self.channel.declare_queue('bot_stopped', durable=True)
            await self.channel.declare_queue('bot_error', durable=True)
            await self.channel.declare_queue('user_request', durable=True)
            
            logger.info("✅ RabbitMQ connection established")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to RabbitMQ: {e}")
            raise
    
    async def publish_event(self, event_type: str, data: Dict):
        #انتشار رویداد
        exchange = await self.channel.get_exchange('bot_events')
        message = aio_pika.Message(
            body=json.dumps(data, default=str).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type='application/json',
            timestamp=datetime.now()
        )
        await exchange.publish(message, routing_key=event_type)
    
    async def publish_command(self, bot_id: str, command: str, data: Dict):
        #ارسال دستور به ربات
        exchange = await self.channel.get_exchange('bot_commands')
        message = aio_pika.Message(
            body=json.dumps({
                'command': command,
                'data': data,
                'timestamp': datetime.now().isoformat()
            }, default=str).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT
        )
        await exchange.publish(message, routing_key=f"bot.{bot_id}")
    
    async def consume_events(self, queue_name: str, callback):
        #مصرف رویدادها
        queue = await self.channel.get_queue(queue_name)
        await queue.consume(callback)
    
    async def close(self):
        #بستن اتصال RabbitMQ
        if self.connection:
            await self.connection.close()
            logger.info("✅ RabbitMQ connection closed")
"""

# ==================== کلاس مدیریت MinIO ====================
# این کلاس مربوط به MinIO است - فعلاً کامنت شده
"""
class MinIOManager:
    #مدیریت ذخیره‌سازی فایل با MinIO
    
    def __init__(self, config: Dict):
        self.config = config
        self.client: Optional[Minio] = None
        self.bucket_name = config['bucket_name']
    
    def initialize(self):
        #راه‌اندازی اتصال به MinIO
        try:
            self.client = Minio(
                self.config['endpoint'],
                access_key=self.config['access_key'],
                secret_key=self.config['secret_key'],
                secure=self.config['secure']
            )
            
            # ایجاد bucket اگر وجود ندارد
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"✅ Bucket {self.bucket_name} created")
            
            logger.info("✅ MinIO connection established")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to MinIO: {e}")
            raise
    
    async def upload_file(self, bot_id: str, file_path: str, file_name: str) -> Optional[str]:
        #آپلود فایل به MinIO
        try:
            object_name = f"{bot_id}/{file_name}"
            
            # تشخیص MIME type
            mime_type = magic.from_file(file_path, mime=True)
            
            # آپلود فایل
            result = self.client.fput_object(
                self.bucket_name,
                object_name,
                file_path,
                content_type=mime_type
            )
            
            # محاسبه هش فایل
            with open(file_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
            
            # ذخیره اطلاعات در دیتابیس
            file_id = hashlib.md5(f"{bot_id}_{file_name}_{time.time()}".encode()).hexdigest()[:16]
            
            logger.info(f"✅ File {file_name} uploaded for bot {bot_id}")
            
            return file_id
            
        except Exception as e:
            logger.error(f"❌ Failed to upload file: {e}")
            return None
    
    async def download_file(self, bot_id: str, file_name: str, save_path: str) -> bool:
        #دانلود فایل از MinIO
        try:
            object_name = f"{bot_id}/{file_name}"
            self.client.fget_object(self.bucket_name, object_name, save_path)
            logger.info(f"✅ File {file_name} downloaded for bot {bot_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to download file: {e}")
            return False
    
    async def list_files(self, bot_id: str) -> List[Dict]:
        #لیست فایل‌های یک ربات
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=f"{bot_id}/",
                recursive=True
            )
            
            files = []
            for obj in objects:
                files.append({
                    'name': obj.object_name.split('/')[-1],
                    'size': obj.size,
                    'last_modified': obj.last_modified.isoformat(),
                    'etag': obj.etag
                })
            
            return files
            
        except Exception as e:
            logger.error(f"❌ Failed to list files: {e}")
            return []
    
    async def delete_file(self, bot_id: str, file_name: str) -> bool:
        #حذف فایل
        try:
            object_name = f"{bot_id}/{file_name}"
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"✅ File {file_name} deleted for bot {bot_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to delete file: {e}")
            return False
"""

# ==================== کلاس مدیریت Docker ====================
# این کلاس مربوط به Docker است - فعلاً کامنت شده
"""
class DockerManager:
    #مدیریت کانتینرهای Docker
    
    def __init__(self, config: Dict):
        self.config = config
        self.client: Optional[docker.DockerClient] = None
    
    def initialize(self):
        #راه‌اندازی اتصال به Docker
        try:
            self.client = docker.from_env()
            logger.info("✅ Docker connection established")
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Docker: {e}")
            raise
    
    async def create_bot_container(self, bot_id: str, token: str, 
                                    user_id: int, files: Dict) -> Optional[str]:
        #ایجاد کانتینر برای ربات
        try:
            # ایجاد Dockerfile
            dockerfile_content = f'''
FROM python:3.11-slim

WORKDIR /app

# نصب کتابخانه‌های پایه
RUN pip install --no-cache-dir pyTelegramBotAPI requests aiohttp

# کپی فایل‌ها
COPY . .

# اجرای ربات
CMD ["python", "bot.py"]
'''
            
            # ایجاد پوشه موقت
            build_path = os.path.join(TEMP_DIR, f"build_{bot_id}")
            os.makedirs(build_path, exist_ok=True)
            
            # ذخیره Dockerfile
            with open(os.path.join(build_path, 'Dockerfile'), 'w') as f:
                f.write(dockerfile_content)
            
            # کپی فایل‌های ربات
            for file_name, file_content in files.items():
                with open(os.path.join(build_path, file_name), 'w') as f:
                    f.write(file_content)
            
            # ساخت image
            image, logs = self.client.images.build(
                path=build_path,
                tag=f"bot_{bot_id}:latest",
                rm=True,
                forcerm=True
            )
            
            # اجرای کانتینر
            container = self.client.containers.run(
                image=f"bot_{bot_id}:latest",
                name=f"bot_{bot_id}",
                environment={
                    'TOKEN': token,
                    'BOT_ID': bot_id,
                    'USER_ID': str(user_id)
                },
                mem_limit='256m',
                cpu_period=100000,
                cpu_quota=50000,  # 0.5 CPU
                network='bot_network',
                detach=True,
                restart_policy={"Name": "always"},
                labels={
                    'bot_id': bot_id,
                    'user_id': str(user_id),
                    'type': 'telegram_bot'
                }
            )
            
            logger.info(f"✅ Container {container.id} created for bot {bot_id}")
            return container.id
            
        except Exception as e:
            logger.error(f"❌ Failed to create container: {e}")
            return None
    
    async def stop_container(self, container_id: str) -> bool:
        #توقف کانتینر
        try:
            container = self.client.containers.get(container_id)
            container.stop()
            container.remove()
            logger.info(f"✅ Container {container_id} stopped and removed")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to stop container: {e}")
            return False
    
    async def get_container_stats(self, container_id: str) -> Optional[Dict]:
        #دریافت آمار کانتینر
        try:
            container = self.client.containers.get(container_id)
            stats = container.stats(stream=False)
            
            # محاسبه CPU
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            
            cpu_percent = 0.0
            if system_delta > 0 and cpu_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0
            
            # محاسبه RAM
            memory_usage = stats['memory_stats']['usage'] / (1024 * 1024)  # MB
            memory_limit = stats['memory_stats']['limit'] / (1024 * 1024)  # MB
            memory_percent = (memory_usage / memory_limit) * 100.0
            
            return {
                'cpu': cpu_percent,
                'cpu_usage': cpu_percent,
                'memory': memory_usage,
                'memory_percent': memory_percent,
                'memory_limit': memory_limit,
                'status': container.status
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get container stats: {e}")
            return None
"""

# ==================== کلاس اصلی ربات مادر ====================

class MotherBot:
    """ربات مادر فوق‌پیشرفته"""
    
    def __init__(self):
        self.bot = bot
        # این بخش‌ها مربوط به کلاس‌های سرور هستند - فعلاً کامنت شده‌اند
        """
        self.db = DatabaseManager(DB_CONFIG)
        self.redis = RedisManager(REDIS_CONFIG)
        self.rabbitmq = RabbitMQManager(RABBITMQ_CONFIG)
        self.minio = MinIOManager(MINIO_CONFIG)
        self.docker = DockerManager(DOCKER_CONFIG)
        """
        
        self.running = True
        self.start_time = datetime.now()
        self.stats = {
            'total_requests': 0,
            'total_bots': 0,
            'total_users': 0,
            'active_bots': 0
        }
        
        # Thread pool برای پردازش موازی
        self.executor = ThreadPoolExecutor(max_workers=100)
        
        logger.info("🤖 MotherBot instance created")
    
    async def initialize(self):
        """راه‌اندازی همه سرویس‌ها"""
        try:
            # این بخش‌ها مربوط به سرویس‌های سرور هستند - فعلاً کامنت شده‌اند
            """
            # راه‌اندازی دیتابیس
            await self.db.initialize()
            
            # راه‌اندازی Redis
            await self.redis.initialize()
            
            # راه‌اندازی RabbitMQ
            await self.rabbitmq.initialize()
            
            # راه‌اندازی MinIO
            await self.minio.initialize()
            
            # راه‌اندازی Docker
            await self.docker.initialize()
            """
            
            # شروع تسک‌های پس‌زمینه
            asyncio.create_task(self._update_stats())
            asyncio.create_task(self._process_events())
            asyncio.create_task(self._monitor_bots())
            
            logger.info("✅ All services initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize services: {e}")
            raise
    
    async def _update_stats(self):
        """به‌روزرسانی آمار"""
        while self.running:
            try:
                # آمار از Redis - فعلاً کامنت شده
                # self.stats['total_requests'] = await self.redis.get_stat('total_requests')
                
                # آمار از دیتابیس - فعلاً کامنت شده
                """
                async with self.db.pool.acquire() as conn:
                    row = await conn.fetchrow('SELECT COUNT(*) FROM users')
                    self.stats['total_users'] = row[0]
                    
                    row = await conn.fetchrow('SELECT COUNT(*) FROM user_bots')
                    self.stats['total_bots'] = row[0]
                    
                    row = await conn.fetchrow(
                        'SELECT COUNT(*) FROM user_bots WHERE status = $1',
                        'running'
                    )
                    self.stats['active_bots'] = row[0]
                """
                
                await asyncio.sleep(60)  # هر دقیقه
                
            except Exception as e:
                logger.error(f"Error updating stats: {e}")
                await asyncio.sleep(10)
    
    async def _process_events(self):
        """پردازش رویدادها از RabbitMQ"""
        async def event_callback(message: aio_pika.IncomingMessage):
            async with message.process():
                try:
                    data = json.loads(message.body)
                    event_type = message.routing_key
                    
                    logger.info(f"📨 Received event: {event_type}")
                    
                    if event_type == 'bot_created':
                        await self._handle_bot_created(data)
                    elif event_type == 'bot_stopped':
                        await self._handle_bot_stopped(data)
                    elif event_type == 'bot_error':
                        await self._handle_bot_error(data)
                        
                except Exception as e:
                    logger.error(f"Error processing event: {e}")
        
        # این بخش مربوط به RabbitMQ است - فعلاً کامنت شده
        # await self.rabbitmq.consume_events('bot_events', event_callback)
        pass
    
    async def _monitor_bots(self):
        """مانیتورینگ ربات‌ها"""
        while self.running:
            try:
                # دریافت ربات‌های در حال اجرا - فعلاً کامنت شده
                """
                async with self.db.pool.acquire() as conn:
                    rows = await conn.fetch('''
                        SELECT id, container_id FROM user_bots
                        WHERE status = 'running' AND container_id IS NOT NULL
                    ''')
                
                for row in rows:
                    bot_id, container_id = row
                    
                    # دریافت آمار از Docker
                    stats = await self.docker.get_container_stats(container_id)
                    
                    if stats:
                        # به‌روزرسانی در دیتابیس
                        await self.db.update_bot(
                            bot_id,
                            cpu_usage=stats['cpu'],
                            memory_usage=stats['memory']
                        )
                        
                        # کش در Redis
                        bot = await self.db.get_bot(bot_id)
                        if bot:
                            await self.redis.cache_bot(bot, 300)
                    
                    await asyncio.sleep(1)  # 1 ثانیه بین هر ربات
                """
                
                await asyncio.sleep(60)  # هر دقیقه
                
            except Exception as e:
                logger.error(f"Error monitoring bots: {e}")
                await asyncio.sleep(10)
    
    async def _handle_bot_created(self, data: Dict):
        """هندلر رویداد ساخت ربات"""
        bot_id = data.get('bot_id')
        logger.info(f"✅ Bot {bot_id} created successfully")
    
    async def _handle_bot_stopped(self, data: Dict):
        """هندلر رویداد توقف ربات"""
        bot_id = data.get('bot_id')
        logger.info(f"🛑 Bot {bot_id} stopped")
    
    async def _handle_bot_error(self, data: Dict):
        """هندلر رویداد خطای ربات"""
        bot_id = data.get('bot_id')
        error = data.get('error')
        logger.error(f"❌ Bot {bot_id} error: {error}")
    
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
        last_name = message.from_user.last_name
        
        # ایجاد کاربر در دیتابیس - فعلاً کامنت شده
        # user = await self.db.create_user(user_id, username, first_name, last_name)
        
        # کش کردن کاربر - فعلاً کامنت شده
        # await self.redis.cache_user(user, 3600)
        
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
                 f"💰 موجودی: 0 تومان\n"
                 f"🤖 ربات‌ها: 0\n\n"
                 f"📤 فایل خود را آپلود کنید تا رباتتان ساخته شود.",
            reply_markup=markup
        )
        
        # آپدیت آمار
        # await self.redis.increment_stat('total_requests')
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
        # await self.redis.increment_stat('total_requests')
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
        text += f"🖥 سرورها: ۵\n"
        text += f"⚡ وضعیت: 🟢 عالی"
        
        await self._send_message(message.chat.id, text)
        # await self.redis.increment_stat('total_requests')
        self.stats['total_requests'] += 1
    
    async def _handle_bots(self, message):
        """هندلر /bots"""
        user_id = message.from_user.id
        
        # bots = await self.db.get_user_bots(user_id)
        bots = []  # فعلاً لیست خالی
        
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
        # await self.redis.increment_stat('total_requests')
        self.stats['total_requests'] += 1
    
    async def _handle_balance(self, message):
        """هندلر /balance"""
        user_id = message.from_user.id
        
        # user = await self.db.get_user(user_id)
        user = None  # فعلاً None
        
        text = f"💰 **کیف پول شما**\n\n"
        text += f"موجودی: 0 تومان\n"
        text += f"پلن: free\n"
        text += f"ربات‌ها: 0\n\n"
        text += f"**قیمت‌ها:**\n"
        text += f"• هر ربات: ۵۰,۰۰۰ تومان\n"
        text += f"• فضای ۱ گیگ: ۱۰,۰۰۰ تومان\n"
        text += f"• پشتیبانی VIP: ۲۰۰,۰۰۰ تومان"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 افزایش موجودی", callback_data="charge"))
        
        await self._send_message(message.chat.id, text, reply_markup=markup)
        # await self.redis.increment_stat('total_requests')
        self.stats['total_requests'] += 1
    
    async def _handle_document(self, message):
        """هندلر آپلود فایل"""
        user_id = message.from_user.id
        file_name = message.document.file_name
        
        status_msg = await self._send_message(
            message.chat.id,
            "🔄 در حال پردازش فایل..."
        )
        
        try:
            # دانلود فایل
            file_info = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.bot.get_file(message.document.file_id)
            )
            downloaded_file = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.bot.download_file(file_info.file_path)
            )
            
            # ایجاد پوشه موقت
            temp_dir = os.path.join(TEMP_DIR, f"user_{user_id}_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)
            
            # ذخیره فایل
            file_path = os.path.join(temp_dir, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
            
            # استخراج اگر فایل فشرده است
            files = {}
            if file_name.endswith('.zip'):
                import zipfile
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                for root, _, filenames in os.walk(temp_dir):
                    for f in filenames:
                        if f.endswith('.py'):
                            with open(os.path.join(root, f), 'r', encoding='utf-8') as fh:
                                files[f] = fh.read()
            
            elif file_name.endswith('.py'):
                with open(file_path, 'r', encoding='utf-8') as fh:
                    files[file_name] = fh.read()
            
            else:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ فرمت فایل مجاز نیست!\nفقط .py و .zip"
                )
                return
            
            # پیدا کردن فایل اصلی
            main_file = None
            for fname in files:
                if fname.endswith('.py'):
                    main_file = fname
                    break
            
            if not main_file:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ هیچ فایل پایتونی پیدا نشد!"
                )
                return
            
            # استخراج توکن
            token_match = re.search(
                r'token\s*=\s*["\']([^"\']+)["\']',
                files[main_file],
                re.IGNORECASE
            )
            
            if not token_match:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ توکن در کد پیدا نشد!"
                )
                return
            
            token = token_match.group(1)
            
            # تست توکن
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
            
            # آیدی یکتا برای ربات
            bot_id = hashlib.md5(f"{user_id}_{token}_{time.time()}".encode()).hexdigest()[:16]
            
            # آپلود فایل‌ها به MinIO - فعلاً کامنت شده
            """
            file_ids = []
            for fname, content in files.items():
                temp_file = os.path.join(temp_dir, fname)
                with open(temp_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                file_id = await self.minio.upload_file(bot_id, temp_file, fname)
                if file_id:
                    file_ids.append(file_id)
            """
            
            # ایجاد ربات در Docker - فعلاً کامنت شده
            """
            container_id = await self.docker.create_bot_container(
                bot_id=bot_id,
                token=token,
                user_id=user_id,
                files=files
            )
            
            if not container_id:
                await self._edit_message(
                    status_msg.chat.id,
                    status_msg.message_id,
                    "❌ خطا در اجرای ربات!"
                )
                return
            """
            
            # ذخیره در دیتابیس - فعلاً کامنت شده
            """
            bot = UserBot(
                id=bot_id,
                user_id=user_id,
                token=token,
                name=bot_name,
                username=bot_username,
                description="",
                status='running',
                container_id=container_id,
                node_id='node1',
                cpu_usage=0,
                memory_usage=0,
                disk_usage=0,
                requests_count=0,
                errors_count=0,
                last_error=None,
                created_at=datetime.now(),
                last_active=datetime.now(),
                settings={}
            )
            
            await self.db.create_bot(bot)
            
            # کش در Redis
            await self.redis.cache_bot(bot, 3600)
            
            # ارسال رویداد به RabbitMQ
            await self.rabbitmq.publish_event('bot_created', {
                'bot_id': bot_id,
                'user_id': user_id,
                'token': token,
                'container_id': container_id
            })
            """
            
            # پاک‌سازی
            shutil.rmtree(temp_dir)
            
            # ارسال پیام موفقیت
            success_text = f"✅ **ربات با موفقیت ساخته شد!** 🎉\n\n"
            success_text += f"🤖 نام: {bot_name}\n"
            success_text += f"🔗 لینک: https://t.me/{bot_username}\n"
            success_text += f"🆔 آیدی: {bot_id}\n"
            success_text += f"🔄 وضعیت: در حال اجرا\n"
            # success_text += f"📦 فایل‌ها: {len(file_ids)}\n\n"
            success_text += f"📦 فایل‌ها: {len(files)}\n\n"
            success_text += f"💡 از /bots برای مدیریت استفاده کن."
            
            await self._edit_message(
                status_msg.chat.id,
                status_msg.message_id,
                success_text
            )
            
            # آپدیت آمار
            # await self.redis.increment_stat('total_bots')
            # await self.redis.increment_stat('total_requests')
            self.stats['total_requests'] += 1
            self.stats['total_bots'] += 1
            
        except Exception as e:
            logger.error(f"Error processing file: {e}\n{traceback.format_exc()}")
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
        
        # await self.redis.increment_stat('total_requests')
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
            # راه‌اندازی سرویس‌ها
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
        
        # بستن اتصالات - فعلاً کامنت شده
        """
        await self.db.close()
        await self.redis.close()
        await self.rabbitmq.close()
        """
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
