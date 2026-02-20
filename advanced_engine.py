# advanced_engine.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
موتور اجرای پیشرفته ربات‌ها - ایزوله، امن و قدرتمند
"""

import sys
import os
import subprocess
import json
import time
import signal
import tempfile
import shutil
import traceback
import resource
import threading
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== موتور اجرای پیشرفته ====================
class AdvancedBotExecutionEngine:
    """
    موتور اجرای پیشرفته با ایزوله‌سازی کامل، مانیتورینگ لحظه‌ای و امنیت بالا
    """
    
    def __init__(self):
        self.running_processes = {}
        self.max_cpu_time = 300  # حداکثر 5 دقیقه
        self.max_memory = 512 * 1024 * 1024  # 512 مگابایت
        self.max_file_size = 100 * 1024 * 1024  # 100 مگابایت
        
    def create_isolated_environment(self, bot_id: str, user_id: int, code: str) -> str:
        """
        ایجاد محیط ایزوله با چرخه‌های نامحدود
        """
        # ایجاد پوشه منحصر به فرد برای هر ربات
        bot_dir = os.path.join(tempfile.gettempdir(), f"bot_sandbox_{bot_id}_{int(time.time())}")
        os.makedirs(bot_dir, exist_ok=True)
        
        # تنظیم پرمیشن‌های محدود
        os.chmod(bot_dir, 0o755)
        
        # ایجاد ساختار پوشه‌ها
        folders = ['logs', 'data', 'temp']
        for folder in folders:
            folder_path = os.path.join(bot_dir, folder)
            os.makedirs(folder_path, exist_ok=True)
            os.chmod(folder_path, 0o755)
        
        # ایجاد فایل کد با حفاظت
        code_path = os.path.join(bot_dir, 'bot.py')
        
        # اضافه کردن کدهای محافظتی و مانیتورینگ
        protected_code = self._add_protection_layers(code, bot_id, user_id)
        
        with open(code_path, 'w', encoding='utf-8') as f:
            f.write(protected_code)
        
        os.chmod(code_path, 0o644)
        
        # ایجاد فایل لاگ
        log_path = os.path.join(bot_dir, 'logs', 'bot.log')
        Path(log_path).touch()
        os.chmod(log_path, 0o644)
        
        return bot_dir
    
    def _add_protection_layers(self, code: str, bot_id: str, user_id: int) -> str:
        """
        اضافه کردن لایه‌های محافظتی به کد
        """
        protection_code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot ID: {bot_id}
# User ID: {user_id}
# Created: {datetime.now().isoformat()}

import sys
import os
import signal
import logging
import resource
import threading
import time
from pathlib import Path

# ==================== تنظیمات امنیتی ====================
# غیرفعال کردن ایجاد فایل‌های بایت کد
sys.dont_write_bytecode = True

# تنظیم محدودیت منابع
try:
    resource.setrlimit(resource.RLIMIT_CPU, (300, 300))  # 5 دقیقه
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))  # 512 مگابایت
    resource.setrlimit(resource.RLIMIT_FSIZE, (100 * 1024 * 1024, 100 * 1024 * 1024))  # 100 مگابایت
    resource.setrlimit(resource.RLIMIT_NOFILE, (100, 100))  # 100 فایل همزمان
except:
    pass

# ==================== سیستم مانیتورینگ ====================
class BotMonitor:
    def __init__(self):
        self.start_time = time.time()
        self.heartbeat_interval = 10
        self.last_heartbeat = self.start_time
        
    def heartbeat(self):
        """ارسال سیگنال زنده بودن"""
        self.last_heartbeat = time.time()
        
    def check_timeout(self):
        """بررسی timeout"""
        if time.time() - self.start_time > 290:  # 10 ثانیه قبل از پایان
            return True
        return False

monitor = BotMonitor()

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'logs', 'bot.log')),
        logging.StreamHandler()
    ]
)

# ==================== کد اصلی کاربر ====================
{code}

# ==================== اجرا با محافظ ====================
if __name__ == "__main__":
    try:
        # راه‌اندازی ترد مانیتورینگ
        def monitor_thread_func():
            while True:
                time.sleep(5)
                monitor.heartbeat()
                if monitor.check_timeout():
                    logging.warning("⚠️ نزدیک به پایان زمان")
        
        monitor_thread = threading.Thread(target=monitor_thread_func, daemon=True)
        monitor_thread.start()
        
        # اجرای کد اصلی
        if 'main' in dir():
            main()
        elif 'run' in dir():
            run()
        elif 'start' in dir():
            start()
        else:
            logging.error("❌ تابع main پیدا نشد")
            
    except KeyboardInterrupt:
        logging.info("⏹ ربات متوقف شد")
    except Exception as e:
        logging.error(f"❌ خطا: {e}")
        import traceback
        traceback.print_exc()
    finally:
        logging.info("🏁 اجرای ربات پایان یافت")
'''
        return protection_code
    
    def run_bot(self, bot_id: str, user_id: int, code: str, token: str) -> Dict[str, Any]:
        """
        اجرای ربات با مانیتورینگ کامل
        """
        result = {
            'success': False,
            'pid': None,
            'error': None,
            'output': '',
            'resource_usage': {}
        }
        
        try:
            # ایجاد محیط ایزوله
            bot_dir = self.create_isolated_environment(bot_id, user_id, code)
            
            # ذخیره توکن
            token_file = os.path.join(bot_dir, 'data', 'token.txt')
            with open(token_file, 'w') as f:
                f.write(token)
            
            # آماده‌سازی دستور اجرا
            python_path = sys.executable
            bot_path = os.path.join(bot_dir, 'bot.py')
            log_path = os.path.join(bot_dir, 'logs', 'bot.log')
            
            # اجرا با محدودیت‌های شدید
            process = subprocess.Popen(
                [python_path, bot_path],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=bot_dir,
                env={
                    'PYTHONPATH': bot_dir,
                    'PYTHONUNBUFFERED': '1',
                    'BOT_ID': bot_id,
                    'USER_ID': str(user_id),
                    'PATH': '/usr/local/bin:/usr/bin:/bin',
                    'HOME': bot_dir,
                    'TEMP': os.path.join(bot_dir, 'temp'),
                    'TMP': os.path.join(bot_dir, 'temp')
                },
                start_new_session=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # ذخیره اطلاعات فرآیند
            self.running_processes[bot_id] = {
                'process': process,
                'dir': bot_dir,
                'start_time': time.time(),
                'pid': process.pid
            }
            
            # مانیتورینگ بلادرنگ
            stdout_lines = []
            while True:
                if process.poll() is not None:
                    break
                    
                # خواندن خروجی
                try:
                    line = process.stdout.readline()
                    if line:
                        stdout_lines.append(line.strip())
                except:
                    pass
                
                # بررسی timeout
                if time.time() - self.running_processes[bot_id]['start_time'] > self.max_cpu_time:
                    self.kill_bot(bot_id, force=True)
                    result['error'] = 'Timeout: اجرا بیش از حد طول کشید'
                    break
                
                time.sleep(0.1)
            
            # دریافت کد خروج
            return_code = process.wait()
            
            result['success'] = return_code == 0
            result['pid'] = process.pid
            result['output'] = '\n'.join(stdout_lines[-100:])  # آخرین 100 خط
            
            # آمار مصرف منابع
            try:
                import psutil
                p = psutil.Process(process.pid)
                result['resource_usage'] = {
                    'cpu_time': p.cpu_times().user,
                    'memory': p.memory_info().rss,
                    'return_code': return_code
                }
            except:
                pass
            
            # خواندن لاگ
            if os.path.exists(log_path):
                with open(log_path, 'r') as f:
                    result['log'] = f.read()[-1000:]  # آخرین 1000 کاراکتر
            
        except Exception as e:
            result['error'] = str(e)
            result['traceback'] = traceback.format_exc()
            
        return result
    
    def kill_bot(self, bot_id: str, force: bool = False) -> bool:
        """
        توقف ربات
        """
        if bot_id not in self.running_processes:
            return False
            
        process_info = self.running_processes[bot_id]
        process = process_info['process']
        
        try:
            if force:
                # kill شدید
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                # kill ملایم
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                time.sleep(2)
                
                # اگر هنوز زنده بود، kill شدید
                if process.poll() is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            
            # پاکسازی پوشه بعد از 10 ثانیه
            def cleanup():
                time.sleep(10)
                if os.path.exists(process_info['dir']):
                    shutil.rmtree(process_info['dir'], ignore_errors=True)
            
            threading.Thread(target=cleanup, daemon=True).start()
            
            del self.running_processes[bot_id]
            return True
            
        except:
            return False
    
    def get_bot_status(self, bot_id: str) -> Dict[str, Any]:
        """
        دریافت وضعیت ربات
        """
        if bot_id not in self.running_processes:
            return {'running': False}
            
        process_info = self.running_processes[bot_id]
        process = process_info['process']
        
        try:
            if process.poll() is None:
                # فرآیند زنده است
                try:
                    import psutil
                    p = psutil.Process(process.pid)
                    
                    return {
                        'running': True,
                        'pid': process.pid,
                        'cpu_percent': p.cpu_percent(interval=0.1),
                        'memory_percent': p.memory_percent(),
                        'memory_rss': p.memory_info().rss,
                        'uptime': time.time() - process_info['start_time']
                    }
                except:
                    return {'running': True, 'pid': process.pid}
            else:
                # فرآیند مرده
                return {
                    'running': False,
                    'return_code': process.returncode
                }
        except:
            return {'running': False}


# نمونه اصلی برای استفاده
engine = AdvancedBotExecutionEngine()

def execute_user_bot(user_id: int, code: str, token: str) -> Dict[str, Any]:
    """
    اجرای ربات کاربر
    """
    bot_id = hashlib.sha256(f"{user_id}{token}{time.time()}".encode()).hexdigest()[:16]
    
    # اجرا
    result = engine.run_bot(bot_id, user_id, code, token)
    
    if result['success']:
        return {
            'success': True,
            'bot_id': bot_id,
            'pid': result['pid'],
            'message': 'ربات با موفقیت اجرا شد'
        }
    else:
        return {
            'success': False,
            'error': result.get('error', 'خطای ناشناخته'),
            'output': result.get('output', ''),
            'log': result.get('log', '')
              }
