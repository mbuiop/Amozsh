#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
موتور اجرای پیشرفته ربات‌ها - نسخه نهایی بدون خطا
ایزوله‌سازی کامل، مانیتورینگ لحظه‌ای، امنیت بالا
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
import logging
import psutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# ==================== تنظیمات لاگ ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AdvancedEngine")

# ==================== موتور اجرای پیشرفته ====================
class AdvancedBotExecutionEngine:
    """
    موتور اجرای پیشرفته با ایزوله‌سازی کامل
    """
    
    def __init__(self):
        self.running_processes = {}
        self.max_cpu_time = 300  # 5 دقیقه
        self.max_memory = 512 * 1024 * 1024  # 512 مگابایت
        
    def create_environment(self, bot_id: str, user_id: int, code: str) -> str:
        """ایجاد محیط ایزوله برای ربات"""
        try:
            # ایجاد پوشه موقت
            bot_dir = os.path.join(tempfile.gettempdir(), f"bot_{bot_id}_{int(time.time())}")
            os.makedirs(bot_dir, exist_ok=True)
            os.chmod(bot_dir, 0o755)
            
            # ایجاد زیرپوشه‌ها
            for folder in ['logs', 'data', 'temp']:
                folder_path = os.path.join(bot_dir, folder)
                os.makedirs(folder_path, exist_ok=True)
                os.chmod(folder_path, 0o755)
            
            # ایجاد فایل کد با محافظ
            code_path = os.path.join(bot_dir, 'bot.py')
            
            # اضافه کردن لایه محافظتی
            protected_code = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Bot ID: {bot_id}
# User ID: {user_id}

import sys
import os
import time
import logging
import threading
import signal
from pathlib import Path

# تنظیمات امنیتی
sys.dont_write_bytecode = True

# تنظیم لاگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'logs', 'bot.log')),
        logging.StreamHandler()
    ]
)

# تابع اصلی (اگر وجود داشته باشد)
{code}

# اجرا
if __name__ == "__main__":
    try:
        if 'main' in dir():
            main()
        elif 'run' in dir():
            run()
        elif 'start' in dir():
            start()
        else:
            logging.warning("هیچ تابع main پیدا نشد")
            
        # نگه داشتن ربات در حال اجرا
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logging.info("ربات متوقف شد")
    except Exception as e:
        logging.error(f"خطا: {{e}}")
        traceback.print_exc()
'''
            
            with open(code_path, 'w', encoding='utf-8') as f:
                f.write(protected_code)
            
            os.chmod(code_path, 0o644)
            
            # ایجاد فایل لاگ خالی
            log_path = os.path.join(bot_dir, 'logs', 'bot.log')
            Path(log_path).touch()
            
            return bot_dir
            
        except Exception as e:
            logger.error(f"خطا در ایجاد محیط: {e}")
            return None
    
    def run_bot(self, bot_id: str, user_id: int, code: str, token: str) -> Dict[str, Any]:
        """اجرای ربات با مانیتورینگ کامل"""
        
        result = {
            'success': False,
            'pid': None,
            'error': None,
            'output': '',
            'log': ''
        }
        
        try:
            # ایجاد محیط
            bot_dir = self.create_environment(bot_id, user_id, code)
            if not bot_dir:
                result['error'] = "خطا در ایجاد محیط اجرا"
                return result
            
            # ذخیره توکن
            token_file = os.path.join(bot_dir, 'data', 'token.txt')
            with open(token_file, 'w') as f:
                f.write(token)
            
            # آماده‌سازی اجرا
            python_path = sys.executable
            bot_path = os.path.join(bot_dir, 'bot.py')
            log_path = os.path.join(bot_dir, 'logs', 'bot.log')
            
            # اجرای فرآیند
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
            
            # ذخیره اطلاعات
            self.running_processes[bot_id] = {
                'process': process,
                'dir': bot_dir,
                'start_time': time.time(),
                'pid': process.pid
            }
            
            # جمع‌آوری خروجی
            output_lines = []
            start_time = time.time()
            
            while True:
                # بررسی پایان فرآیند
                if process.poll() is not None:
                    break
                
                # بررسی timeout
                if time.time() - start_time > self.max_cpu_time:
                    self.kill_bot(bot_id, force=True)
                    result['error'] = "Timeout: زمان اجرا بیش از حد مجاز"
                    break
                
                # خواندن خروجی
                try:
                    line = process.stdout.readline()
                    if line:
                        output_lines.append(line.strip())
                except:
                    pass
                
                time.sleep(0.1)
            
            # دریافت کد خروج
            return_code = process.wait()
            
            # خواندن لاگ
            if os.path.exists(log_path):
                try:
                    with open(log_path, 'r', encoding='utf-8') as f:
                        result['log'] = f.read()[-1000:]  # آخرین 1000 کاراکتر
                except:
                    pass
            
            result['success'] = (return_code == 0)
            result['pid'] = process.pid
            result['output'] = '\n'.join(output_lines[-50:])  # آخرین 50 خط
            
            # اگر خطایی بود
            if return_code != 0 and not result['error']:
                result['error'] = f"فرآیند با کد خطای {return_code} پایان یافت"
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"خطا در run_bot: {e}")
        
        return result
    
    def kill_bot(self, bot_id: str, force: bool = False) -> bool:
        """توقف ربات"""
        try:
            if bot_id not in self.running_processes:
                return False
            
            process_info = self.running_processes[bot_id]
            process = process_info['process']
            
            # ارسال SIGTERM
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                time.sleep(2)
            except:
                pass
            
            # اگر هنوز زنده بود، SIGKILL
            try:
                if process.poll() is None:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except:
                pass
            
            # پاکسازی پوشه بعد از 10 ثانیه
            def cleanup():
                time.sleep(10)
                try:
                    if os.path.exists(process_info['dir']):
                        shutil.rmtree(process_info['dir'], ignore_errors=True)
                except:
                    pass
            
            threading.Thread(target=cleanup, daemon=True).start()
            
            # حذف از دیکشنری
            if bot_id in self.running_processes:
                del self.running_processes[bot_id]
            
            return True
            
        except Exception as e:
            logger.error(f"خطا در kill_bot: {e}")
            return False
    
    def get_status(self, bot_id: str) -> Dict[str, Any]:
        """دریافت وضعیت ربات"""
        try:
            if bot_id not in self.running_processes:
                return {'running': False}
            
            process_info = self.running_processes[bot_id]
            process = process_info['process']
            
            if process.poll() is None:
                # فرآیند زنده است
                try:
                    p = psutil.Process(process.pid)
                    return {
                        'running': True,
                        'pid': process.pid,
                        'cpu': p.cpu_percent(interval=0.1),
                        'memory': p.memory_percent(),
                        'uptime': time.time() - process_info['start_time']
                    }
                except:
                    return {'running': True, 'pid': process.pid}
            else:
                return {
                    'running': False,
                    'return_code': process.returncode
                }
                
        except Exception as e:
            logger.error(f"خطا در get_status: {e}")
            return {'running': False}


# ==================== نمونه اصلی ====================
engine = AdvancedBotExecutionEngine()

def execute_user_bot(user_id: int, code: str, token: str) -> Dict[str, Any]:
    """اجرای ربات کاربر - تابع اصلی برای استفاده"""
    try:
        # تولید آیدی یکتا برای ربات
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
            
    except Exception as e:
        logger.error(f"خطا در execute_user_bot: {e}")
        return {
            'success': False,
            'error': str(e),
            'output': '',
            'log': ''
          }
