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
from datetime import datetime
from pathlib import Path
import logging
from logging.handlers import RotatingFileHandler

# ==================== تنظیمات پیشرفته ====================
TOKEN = "8052349235:AAFSaJmYpl359BKrJTWC8O-u-dI9r2olEOQ"
bot = telebot.TeleBot(TOKEN)
bot.delete_webhook()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_DIR = os.path.join(BASE_DIR, "users")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
REQUESTS_DIR = os.path.join(BASE_DIR, "requests")
os.makedirs(USERS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
os.makedirs(REQUESTS_DIR, exist_ok=True)

# ==================== لاگینگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler(os.path.join(LOGS_DIR, 'mother.log'), maxBytes=10485760, backupCount=10),
        logging.StreamHandler()
    ]
)

# ==================== دیتابیس ====================
conn = sqlite3.connect('mother.db', check_same_thread=False)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    email TEXT,
    phone TEXT,
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    total_bots INTEGER DEFAULT 0,
    total_requests INTEGER DEFAULT 0
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    bot_token TEXT UNIQUE,
    bot_name TEXT,
    bot_username TEXT,
    bot_folder TEXT,
    pid INTEGER,
    port INTEGER,
    cpu_usage REAL DEFAULT 0,
    memory_usage REAL DEFAULT 0,
    status TEXT DEFAULT 'stopped',
    created_at TIMESTAMP,
    last_active TIMESTAMP,
    error_log TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    file_name TEXT,
    file_path TEXT,
    file_size INTEGER,
    file_hash TEXT,
    uploaded_at TIMESTAMP,
    FOREIGN KEY(bot_id) REFERENCES bots(id)
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS libraries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    lib_name TEXT,
    lib_version TEXT,
    installed_at TIMESTAMP,
    FOREIGN KEY(bot_id) REFERENCES bots(id)
)
''')

c.execute('''
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER,
    user_id INTEGER,
    command TEXT,
    response_time REAL,
    created_at TIMESTAMP,
    FOREIGN KEY(bot_id) REFERENCES bots(id)
)
''')
conn.commit()

# ==================== کش ====================
class Cache:
    def __init__(self, max_size=10000):
        self.cache = {}
        self.max_size = max_size
    
    def get(self, key):
        return self.cache.get(key)
    
    def set(self, key, value, ttl=300):
        if len(self.cache) >= self.max_size:
            oldest = min(self.cache.keys(), key=lambda k: self.cache[k][1])
            del self.cache[oldest]
        self.cache[key] = (value, time.time() + ttl)
    
    def clean(self):
        now = time.time()
        self.cache = {k: v for k, v in self.cache.items() if v[1] > now}

cache = Cache()

# ==================== Rate Limiter پیشرفته ====================
class AdvancedRateLimiter:
    def __init__(self, max_requests=30, window=1):
        self.max_requests = max_requests
        self.window = window
        self.requests = {}
        self.lock = threading.Lock()
    
    def allow(self, user_id):
        with self.lock:
            now = time.time()
            if user_id not in self.requests:
                self.requests[user_id] = []
            
            self.requests[user_id] = [t for t in self.requests[user_id] if t > now - self.window]
            
            if len(self.requests[user_id]) >= self.max_requests:
                return False
            
            self.requests[user_id].append(now)
            return True
    
    def get_wait_time(self, user_id):
        with self.lock:
            if user_id not in self.requests:
                return 0
            if len(self.requests[user_id]) < self.max_requests:
                return 0
            return self.requests[user_id][0] + self.window - time.time()

rate_limiter = AdvancedRateLimiter(25, 1)

# ==================== Resource Monitor ====================
class ResourceMonitor:
    def __init__(self):
        self.max_cpu = 80
        self.max_memory = 80
        self.max_disk = 90
    
    def check(self):
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent
        
        warnings = []
        if cpu > self.max_cpu:
            warnings.append(f"CPU: {cpu}%")
        if memory > self.max_memory:
            warnings.append(f"RAM: {memory}%")
        if disk > self.max_disk:
            warnings.append(f"Disk: {disk}%")
        
        return {
            'cpu': cpu,
            'memory': memory,
            'disk': disk,
            'healthy': len(warnings) == 0,
            'warnings': warnings
        }

resource_monitor = ResourceMonitor()

# ==================== Library Manager ====================
class LibraryManager:
    def __init__(self):
        self.common_libs = {
            'telebot': 'pyTelegramBotAPI',
            'requests': 'requests',
            'flask': 'Flask',
            'django': 'Django',
            'numpy': 'numpy',
            'pandas': 'pandas',
            'pillow': 'Pillow',
            'bs4': 'beautifulsoup4',
            'selenium': 'selenium',
            'sqlalchemy': 'SQLAlchemy',
            'redis': 'redis',
            'pymongo': 'pymongo',
            'matplotlib': 'matplotlib',
            'tensorflow': 'tensorflow',
            'torch': 'torch',
            'opencv': 'opencv-python',
            'moviepy': 'moviepy',
            'qrcode': 'qrcode[pil]',
            'reportlab': 'reportlab',
            'openpyxl': 'openpyxl',
            'pytz': 'pytz',
            'jdatetime': 'jdatetime',
            'aiohttp': 'aiohttp',
            'asyncio': 'asyncio',
            'websockets': 'websockets',
            'fastapi': 'fastapi',
            'uvicorn': 'uvicorn',
            'gunicorn': 'gunicorn',
            'celery': 'celery',
            'sqlite3': 'sqlite3',
            'psycopg2': 'psycopg2-binary',
            'pymysql': 'pymysql',
        }
    
    def extract_imports(self, code):
        imports = set()
        patterns = [
            r'^import\s+([a-zA-Z0-9_]+)',
            r'^from\s+([a-zA-Z0-9_]+)\s+import',
            r'__import__\([\'"]([a-zA-Z0-9_]+)[\'"]\)',
        ]
        
        for line in code.split('\n'):
            line = line.strip()
            for pattern in patterns:
                match = re.match(pattern, line)
                if match:
                    imports.add(match.group(1))
        
        return list(imports)
    
    def get_required_libs(self, code):
        imports = self.extract_imports(code)
        required = []
        
        for imp in imports:
            if imp in self.common_libs:
                required.append({
                    'name': imp,
                    'pip': self.common_libs[imp],
                    'status': 'not_installed'
                })
            elif imp in sys.modules:
                required.append({
                    'name': imp,
                    'pip': imp,
                    'status': 'builtin'
                })
        
        return required
    
    def install_library(self, lib_name, target_dir):
        try:
            # نصب در محیط مجازی کاربر
            venv_dir = os.path.join(target_dir, 'venv')
            if not os.path.exists(venv_dir):
                subprocess.run([sys.executable, '-m', 'venv', venv_dir], check=True)
            
            pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
            
            result = subprocess.run(
                [pip_path, 'install', lib_name],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=target_dir
            )
            
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Timeout: نصب بیش از ۲ دقیقه طول کشید"
        except Exception as e:
            return False, str(e)
    
    def get_suggestion_list(self):
        return [
            {"name": "pyTelegramBotAPI", "desc": "ربات تلگرام", "popular": 10000},
            {"name": "requests", "desc": "درخواست HTTP", "popular": 9500},
            {"name": "Flask", "desc": "وب‌سایت", "popular": 9000},
            {"name": "beautifulsoup4", "desc": "استخراج از وب", "popular": 8500},
            {"name": "Pillow", "desc": "پردازش تصویر", "popular": 8000},
            {"name": "pandas", "desc": "تحلیل داده", "popular": 7500},
            {"name": "numpy", "desc": "محاسبات عددی", "popular": 7000},
            {"name": "matplotlib", "desc": "نمودار", "popular": 6500},
            {"name": "qrcode", "desc": "ساخت QR", "popular": 6000},
            {"name": "jdatetime", "desc": "تاریخ شمسی", "popular": 5500},
        ]

lib_manager = LibraryManager()

# ==================== File Processor ====================
class FileProcessor:
    def __init__(self):
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.allowed_extensions = {'.py', '.zip', '.tar', '.tar.gz', '.tgz', '.rar'}
    
    def process_upload(self, message, user_id):
        try:
            file_name = message.document.file_name
            file_ext = os.path.splitext(file_name)[1].lower()
            
            if file_ext not in self.allowed_extensions:
                return False, f"❌ فرمت مجاز نیست! مجاز: {', '.join(self.allowed_extensions)}"
            
            file_info = bot.get_file(message.document.file_id)
            if file_info.file_size > self.max_file_size:
                return False, f"❌ حجم فایل بیش از ۵۰MB است!"
            
            # دانلود فایل
            downloaded_file = bot.download_file(file_info.file_path)
            
            # ایجاد پوشه برای کاربر
            user_folder = os.path.join(USERS_DIR, str(user_id))
            bot_folder = os.path.join(user_folder, f"bot_{int(time.time())}")
            os.makedirs(bot_folder, exist_ok=True)
            
            # ذخیره فایل اصلی
            file_path = os.path.join(bot_folder, file_name)
            with open(file_path, 'wb') as f:
                f.write(downloaded_file)
            
            # استخراج اگر فایل فشرده است
            if file_ext in {'.zip', '.tar', '.tar.gz', '.tgz', '.rar'}:
                extracted = self.extract_archive(file_path, bot_folder)
                if not extracted:
                    return False, "❌ خطا در استخراج فایل فشرده!"
            
            # پیدا کردن فایل‌های پایتون
            py_files = self.find_py_files(bot_folder)
            
            if not py_files:
                return False, "❌ هیچ فایل پایتونی پیدا نشد!"
            
            return True, {
                'folder': bot_folder,
                'files': py_files,
                'main_file': py_files[0]  # فایل اصلی
            }
            
        except Exception as e:
            logging.error(f"File process error: {e}")
            return False, str(e)
    
    def extract_archive(self, archive_path, extract_to):
        try:
            if archive_path.endswith('.zip'):
                with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_to)
            elif archive_path.endswith('.tar'):
                with tarfile.open(archive_path, 'r') as tar_ref:
                    tar_ref.extractall(extract_to)
            elif archive_path.endswith(('.tar.gz', '.tgz')):
                with tarfile.open(archive_path, 'r:gz') as tar_ref:
                    tar_ref.extractall(extract_to)
            elif archive_path.endswith('.rar'):
                # نیاز به unrar
                subprocess.run(['unrar', 'x', archive_path, extract_to], check=True)
            return True
        except Exception as e:
            logging.error(f"Extract error: {e}")
            return False
    
    def find_py_files(self, folder):
        py_files = []
        for root, dirs, files in os.walk(folder):
            for file in files:
                if file.endswith('.py'):
                    py_files.append(os.path.join(root, file))
        return py_files
    
    def validate_python_code(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            compile(code, file_path, 'exec')
            return True, None
        except SyntaxError as e:
            return False, str(e)
        except Exception as e:
            return False, str(e)
    
    def extract_token_from_code(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            patterns = [
                r'token\s*=\s*["\']([^"\']+)["\']',
                r'TOKEN\s*=\s*["\']([^"\']+)["\']',
                r'API_TOKEN\s*=\s*["\']([^"\']+)["\']',
                r'BOT_TOKEN\s*=\s*["\']([^"\']+)["\']',
                r'bot\s*=\s*telebot\.TeleBot\(\s*["\']([^"\']+)["\']\s*\)',
                r'application\s*=\s*telebot\.TeleBot\(\s*["\']([^"\']+)["\']\s*\)',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, code, re.IGNORECASE)
                if match:
                    return match.group(1)
            return None
        except Exception as e:
            logging.error(f"Token extraction error: {e}")
            return None

file_processor = FileProcessor()

# ==================== Bot Executor ====================
class BotExecutor:
    def __init__(self):
        self.max_bots_per_user = 10
        self.max_bots_total = 10000
        self.running_bots = {}
    
    def execute(self, user_id, bot_folder, main_file):
        try:
            # بررسی محدودیت‌ها
            if len(self.running_bots) >= self.max_bots_total:
                return False, "❌ سرور پر است! لطفاً بعداً امتحان کنید."
            
            c.execute('SELECT COUNT(*) FROM bots WHERE user_id = ? AND status = "running"', (user_id,))
            user_bots = c.fetchone()[0]
            if user_bots >= self.max_bots_per_user:
                return False, f"❌ حداکثر {self.max_bots_per_user} ربات همزمان می‌توانید داشته باشید!"
            
            # بررسی منابع
            resources = resource_monitor.check()
            if not resources['healthy']:
                return False, f"❌ سرور شلوغ است! {', '.join(resources['warnings'])}"
            
            # استخراج توکن
            token = file_processor.extract_token_from_code(main_file)
            if not token:
                return False, "❌ توکن در کد پیدا نشد!"
            
            # تست توکن
            import requests
            response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if response.status_code != 200:
                return False, "❌ توکن معتبر نیست!"
            
            bot_info = response.json()['result']
            bot_name = bot_info['first_name']
            bot_username = bot_info['username']
            
            # ایجاد محیط مجازی
            venv_dir = os.path.join(bot_folder, 'venv')
            subprocess.run([sys.executable, '-m', 'venv', venv_dir], check=True)
            
            # نصب کتابخانه‌های ضروری
            pip_path = os.path.join(venv_dir, 'bin', 'pip') if os.name != 'nt' else os.path.join(venv_dir, 'Scripts', 'pip.exe')
            subprocess.run([pip_path, 'install', '--upgrade', 'pip'], capture_output=True)
            subprocess.run([pip_path, 'install', 'pyTelegramBotAPI', 'requests'], capture_output=True)
            
            # نصب کتابخانه‌های مورد نیاز کد
            with open(main_file, 'r', encoding='utf-8') as f:
                code = f.read()
            required_libs = lib_manager.get_required_libs(code)
            
            installed = []
            failed = []
            for lib in required_libs:
                if lib['status'] == 'not_installed':
                    success, _ = lib_manager.install_library(lib['pip'], bot_folder)
                    if success:
                        installed.append(lib['name'])
                    else:
                        failed.append(lib['name'])
            
            # ذخیره توکن
            with open(os.path.join(bot_folder, "token.txt"), 'w') as f:
                f.write(token)
            
            # پیدا کردن پورت آزاد
            port = self.find_free_port()
            
            # ایجاد فایل اجرایی
            run_file = os.path.join(bot_folder, "run.py")
            with open(run_file, 'w', encoding='utf-8') as f:
                f.write(f'''#!/usr/bin/env python3
import os
import sys
import site

# استفاده از محیط مجازی
venv_path = os.path.join(os.path.dirname(__file__), 'venv')
site.addsitedir(os.path.join(venv_path, 'lib', 'python{sys.version_info.major}.{sys.version_info.minor}', 'site-packages'))

# اجرای فایل اصلی
with open('{os.path.basename(main_file)}', 'r', encoding='utf-8') as f:
    exec(f.read())
''')
            
            os.chmod(run_file, 0o755)
            
            # اجرا با محیط مجازی
            process = subprocess.Popen(
                [sys.executable, run_file],
                stdout=open(os.path.join(bot_folder, "output.log"), 'w'),
                stderr=subprocess.STDOUT,
                cwd=bot_folder,
                env={**os.environ, 'PORT': str(port)},
                start_new_session=True
            )
            
            # ذخیره در دیتابیس
            c.execute('''
                INSERT INTO bots 
                (user_id, bot_token, bot_name, bot_username, bot_folder, pid, port, status, created_at, last_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, token, bot_name, bot_username, bot_folder, process.pid, port, 'running', datetime.now(), datetime.now()))
            bot_id = c.lastrowid
            conn.commit()
            
            # ثبت فایل‌ها
            for file_path in file_processor.find_py_files(bot_folder):
                file_hash = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
                c.execute('''
                    INSERT INTO files (bot_id, file_name, file_path, file_size, file_hash, uploaded_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (bot_id, os.path.basename(file_path), file_path, os.path.getsize(file_path), file_hash, datetime.now()))
            conn.commit()
            
            # ثبت کتابخانه‌ها
            for lib in installed:
                c.execute('''
                    INSERT INTO libraries (bot_id, lib_name, installed_at)
                    VALUES (?, ?, ?)
                ''', (bot_id, lib, datetime.now()))
            conn.commit()
            
            self.running_bots[process.pid] = {
                'bot_id': bot_id,
                'user_id': user_id,
                'folder': bot_folder,
                'port': port,
                'started': time.time()
            }
            
            return True, {
                'bot_id': bot_id,
                'name': bot_name,
                'username': bot_username,
                'pid': process.pid,
                'port': port,
                'installed': installed,
                'failed': failed
            }
            
        except Exception as e:
            logging.error(f"Execute error: {e}")
            return False, str(e)
    
    def find_free_port(self):
        import socket
        from contextlib import closing
        
        for port in range(8000, 9000):
            with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
                if sock.connect_ex(('localhost', port)) != 0:
                    return port
        return 8080
    
    def stop_bot(self, pid):
        try:
            if pid in self.running_bots:
                os.killpg(os.getpgid(pid), signal.SIGTERM)
                del self.running_bots[pid]
                return True
            return False
        except:
            return False
    
    def monitor(self):
        while True:
            to_remove = []
            for pid, info in self.running_bots.items():
                try:
                    os.kill(pid, 0)
                    
                    # آپدیت مصرف منابع
                    try:
                        proc = psutil.Process(pid)
                        cpu = proc.cpu_percent()
                        memory = proc.memory_percent()
                        
                        c.execute('''
                            UPDATE bots SET cpu_usage = ?, memory_usage = ?, last_active = ?
                            WHERE pid = ?
                        ''', (cpu, memory, datetime.now(), pid))
                        conn.commit()
                    except:
                        pass
                    
                except:
                    to_remove.append(pid)
                    c.execute('UPDATE bots SET status = ? WHERE pid = ?', ('stopped', pid))
                    conn.commit()
            
            for pid in to_remove:
                del self.running_bots[pid]
            
            time.sleep(10)

executor = BotExecutor()
monitor_thread = threading.Thread(target=executor.monitor, daemon=True)
monitor_thread.start()

# ==================== شروع ربات ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "کاربر"
    
    c.execute('''
        INSERT OR IGNORE INTO users (user_id, username, created_at, last_active)
        VALUES (?, ?, ?, ?)
    ''', (user_id, username, datetime.now(), datetime.now()))
    
    c.execute('''
        UPDATE users SET last_active = ? WHERE user_id = ?
    ''', (datetime.now(), user_id))
    conn.commit()
    
    if not rate_limiter.allow(user_id):
        wait = rate_limiter.get_wait_time(user_id)
        bot.send_message(
            message.chat.id,
            f"⏱ لطفاً {wait:.1f} ثانیه صبر کنید..."
        )
        return
    
    resources = resource_monitor.check()
    
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton('📤 آپلود فایل'),
        types.KeyboardButton('📚 کتابخانه‌ها'),
        types.KeyboardButton('📋 ربات‌های من'),
        types.KeyboardButton('📊 وضعیت سرور'),
        types.KeyboardButton('💰 کیف پول'),
        types.KeyboardButton('📞 پشتیبانی')
    )
    
    bot.send_message(
        message.chat.id,
        f"🚀 **به ربات مادر حرفه‌ای خوش آمدید!**\n\n"
        f"👤 کاربر: {username}\n"
        f"🆔 آیدی: {user_id}\n"
        f"📊 وضعیت سرور: {'🟢 عالی' if resources['healthy'] else '🟡 شلوغ'}\n\n"
        f"**✨ امکانات:**\n"
        f"✅ آپلود فایل .py یا فایل فشرده\n"
        f"✅ پشتیبانی از چندین فایل\n"
        f"✅ محیط مجازی جداگانه برای هر ربات\n"
        f"✅ نصب خودکار کتابخانه‌ها\n"
        f"✅ مانیتورینگ منابع\n"
        f"✅ ۱۰ کتابخانه پیشنهادی\n\n"
        f"📤 فایل خود را آپلود کنید تا رباتتان ساخته شود.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda m: m.text == '📤 آپلود فایل')
def upload_file(message):
    bot.send_message(
        message.chat.id,
        "📤 **فایل خود را ارسال کنید**\n\n"
        "✅ فرمت‌های مجاز:\n"
        "• `.py` - فایل پایتون\n"
        "• `.zip` - فایل فشرده\n"
        "• `.tar`, `.tar.gz` - فایل فشرده\n"
        "• `.rar` - فایل فشرده\n\n"
        "📦 حداکثر حجم: ۵۰ مگابایت\n"
        "📁 پشتیبانی از چندین فایل\n\n"
        "🔍 پس از آپلود:\n"
        "1️⃣ بررسی خطاهای نحوی\n"
        "2️⃣ استخراج خودکار توکن\n"
        "3️⃣ ایجاد محیط مجازی\n"
        "4️⃣ نصب کتابخانه‌ها\n"
        "5️⃣ اجرای ربات",
        parse_mode="Markdown"
    )

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    
    if not rate_limiter.allow(user_id):
        wait = rate_limiter.get_wait_time(user_id)
        bot.reply_to(
            message,
            f"⏱ لطفاً {wait:.1f} ثانیه صبر کنید..."
        )
        return
    
    status_msg = bot.reply_to(message, "🔄 در حال پردازش فایل...")
    
    try:
        # پردازش فایل
        success, result = file_processor.process_upload(message, user_id)
        
        if not success:
            bot.edit_message_text(
                f"❌ {result}",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        bot.edit_message_text(
            f"✅ فایل با موفقیت پردازش شد!\n"
            f"📁 {len(result['files'])} فایل پایتون پیدا شد.\n\n"
            f"🔄 در حال بررسی کد...",
            message.chat.id,
            status_msg.message_id
        )
        
        # اعتبارسنجی فایل اصلی
        valid, error = file_processor.validate_python_code(result['main_file'])
        if not valid:
            bot.edit_message_text(
                f"❌ خطای نحوی در فایل:\n```\n{error}\n```",
                message.chat.id,
                status_msg.message_id,
                parse_mode="Markdown"
            )
            return
        
        bot.edit_message_text(
            f"✅ کد از نظر نحوی سالم است.\n\n"
            f"🔄 در حال اجرای ربات...",
            message.chat.id,
            status_msg.message_id
        )
        
        # اجرای ربات
        exec_success, exec_result = executor.execute(
            user_id,
            result['folder'],
            result['main_file']
        )
        
        if not exec_success:
            bot.edit_message_text(
                f"❌ خطا در اجرا:\n{exec_result}",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # آپدیت آمار کاربر
        c.execute('''
            UPDATE users SET total_bots = total_bots + 1, total_requests = total_requests + 1
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        
        # نمایش کتابخانه‌های پیشنهادی
        suggestions = lib_manager.get_suggestion_list()
        
        text = f"✅ **ربات با موفقیت اجرا شد!** 🎉\n\n"
        text += f"🤖 نام: {exec_result['name']}\n"
        text += f"🔗 لینک: https://t.me/{exec_result['username']}\n"
        text += f"🆔 آیدی: {exec_result['bot_id']}\n"
        text += f"🔄 PID: {exec_result['pid']}\n"
        text += f"🔌 پورت: {exec_result['port']}\n"
        text += f"📊 وضعیت: در حال اجرا\n\n"
        
        if exec_result['installed']:
            text += f"✅ کتابخانه‌های نصب شده:\n"
            for lib in exec_result['installed']:
                text += f"   • {lib}\n"
            text += "\n"
        
        if exec_result['failed']:
            text += f"❌ کتابخانه‌های نصب نشده:\n"
            for lib in exec_result['failed']:
                text += f"   • {lib}\n"
            text += "\n"
        
        text += f"📚 **کتابخانه‌های پیشنهادی:**\n"
        for lib in suggestions[:5]:
            text += f"   • {lib['name']} - {lib['desc']}\n"
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        for lib in suggestions[:10]:
            btn = types.InlineKeyboardButton(
                f"📦 {lib['name']}",
                callback_data=f"install_{exec_result['bot_id']}_{lib['name']}"
            )
            markup.add(btn)
        
        bot.edit_message_text(
            text,
            message.chat.id,
            status_msg.message_id,
            reply_markup=markup,
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logging.error(f"Handle file error: {e}")
        bot.edit_message_text(
            f"❌ خطای سیستمی:\n{str(e)}",
            message.chat.id,
            status_msg.message_id
        )

@bot.callback_query_handler(func=lambda call: call.data.startswith('install_'))
def install_library(call):
    parts = call.data.split('_')
    bot_id = int(parts[1])
    lib_name = '_'.join(parts[2:])
    
    user_id = call.from_user.id
    
    # بررسی مالکیت
    c.execute('SELECT user_id, bot_folder FROM bots WHERE id = ?', (bot_id,))
    result = c.fetchone()
    if not result or result[0] != user_id:
        bot.answer_callback_query(call.id, "❌ شما مالک این ربات نیستید!")
        return
    
    bot_folder = result[1]
    
    bot.edit_message_text(
        f"🔄 در حال نصب {lib_name}...",
        call.message.chat.id,
        call.message.message_id
    )
    
    success, output = lib_manager.install_library(lib_name, bot_folder)
    
    if success:
        c.execute('''
            INSERT INTO libraries (bot_id, lib_name, installed_at)
            VALUES (?, ?, ?)
        ''', (bot_id, lib_name, datetime.now()))
        conn.commit()
        
        bot.edit_message_text(
            f"✅ کتابخانه {lib_name} با موفقیت نصب شد!",
            call.message.chat.id,
            call.message.message_id
        )
    else:
        bot.edit_message_text(
            f"❌ خطا در نصب {lib_name}:\n{output}",
            call.message.chat.id,
            call.message.message_id
        )

@bot.message_handler(func=lambda m: m.text == '📚 کتابخانه‌ها')
def show_libraries(message):
    suggestions = lib_manager.get_suggestion_list()
    
    text = "📚 **۱۰ کتابخانه پرطرفدار:**\n\n"
    for lib in suggestions:
        text += f"• `{lib['name']}` - {lib['desc']}\n"
        text += f"  ⭐ {lib['popular']} نصب\n\n"
    
    text += "\n💡 می‌توانید با دستور `/install <lib>` نصب کنید."
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '📋 ربات‌های من')
def my_bots(message):
    user_id = message.from_user.id
    
    c.execute('''
        SELECT id, bot_name, bot_username, status, cpu_usage, memory_usage, created_at
        FROM bots WHERE user_id = ? ORDER BY id DESC LIMIT 10
    ''', (user_id,))
    
    bots = c.fetchall()
    
    if not bots:
        bot.send_message(
            message.chat.id,
            "📋 شما هنوز رباتی نساخته‌اید!"
        )
        return
    
    text = "📋 **ربات‌های شما:**\n\n"
    for bot_id, name, username, status, cpu, mem, created in bots:
        emoji = "🟢" if status == 'running' else "🔴" if status == 'error' else "🟡"
        text += f"{emoji} **{name}**\n"
        text += f"   🔗 https://t.me/{username}\n"
        text += f"   🆔 {bot_id}\n"
        text += f"   💻 CPU: {cpu:.1f}% | RAM: {mem:.1f}%\n"
        text += f"   📅 {created[:16]}\n\n"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '📊 وضعیت سرور')
def server_status(message):
    resources = resource_monitor.check()
    
    c.execute('SELECT COUNT(*) FROM bots WHERE status = "running"')
    running_bots = c.fetchone()[0]
    
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    
    text = "📊 **وضعیت سرور**\n\n"
    text += f"🖥 CPU: {resources['cpu']}%\n"
    text += f"💾 RAM: {resources['memory']}%\n"
    text += f"📀 Disk: {resources['disk']}%\n"
    text += f"🤖 ربات‌های فعال: {running_bots}\n"
    text += f"👥 کاربران کل: {total_users}\n"
    text += f"⚡ وضعیت: {'🟢 عالی' if resources['healthy'] else '🟡 شلوغ'}\n"
    
    if not resources['healthy']:
        text += f"\n⚠️ هشدار: {', '.join(resources['warnings'])}"
    
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['stop'])
def stop_bot(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ لطفاً آیدی ربات را وارد کنید:\n/stop <bot_id>")
        return
    
    try:
        bot_id = int(parts[1])
    except:
        bot.reply_to(message, "❌ آیدی ربات باید عدد باشد!")
        return
    
    user_id = message.from_user.id
    
    c.execute('SELECT pid FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id))
    result = c.fetchone()
    
    if not result:
        bot.reply_to(message, "❌ ربات پیدا نشد!")
        return
    
    if executor.stop_bot(result[0]):
        c.execute('UPDATE bots SET status = ? WHERE id = ?', ('stopped', bot_id))
        conn.commit()
        bot.reply_to(message, f"✅ ربات {bot_id} متوقف شد.")
    else:
        bot.reply_to(message, "❌ خطا در توقف ربات!")

@bot.message_handler(commands=['logs'])
def show_logs(message):
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "❌ لطفاً آیدی ربات را وارد کنید:\n/logs <bot_id>")
        return
    
    try:
        bot_id = int(parts[1])
    except:
        bot.reply_to(message, "❌ آیدی ربات باید عدد باشد!")
        return
    
    user_id = message.from_user.id
    
    c.execute('SELECT bot_folder FROM bots WHERE id = ? AND user_id = ?', (bot_id, user_id))
    result = c.fetchone()
    
    if not result:
        bot.reply_to(message, "❌ ربات پیدا نشد!")
        return
    
    log_file = os.path.join(result[0], "output.log")
    
    if os.path.exists(log_file):
        with open(log_file, 'r', encoding='utf-8') as f:
            logs = f.read()[-2000:]  # آخرین 2000 کاراکتر
        bot.send_message(
            message.chat.id,
            f"📋 **آخرین لاگ‌های ربات {bot_id}:**\n```\n{logs}\n```",
            parse_mode="Markdown"
        )
    else:
        bot.send_message(message.chat.id, "📋 لاگی وجود ندارد.")

# ==================== اجرا ====================
if __name__ == "__main__":
    logging.info("🚀 ربات مادر حرفه‌ای راه‌اندازی شد...")
    logging.info(f"📁 پوشه کاربران: {USERS_DIR}")
    logging.info(f"📁 پوشه لاگ‌ها: {LOGS_DIR}")
    
    # پاک‌سازی کش هر ساعت
    def clean_cache():
        while True:
            cache.clean()
            time.sleep(3600)
    
    threading.Thread(target=clean_cache, daemon=True).start()
    
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"❌ خطا: {e}")
            time.sleep(5)
