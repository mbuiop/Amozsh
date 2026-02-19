import sqlite3
import os
import time
import signal
import psutil
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'master_bot.db')

def monitor_bots():
    """مانیتورینگ و راه‌اندازی مجدد ربات‌های crashed"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    while True:
        c.execute('''SELECT id, pid FROM user_bots WHERE status = 'running' ''')
        bots = c.fetchall()
        
        for bot_id, pid in bots:
            if not psutil.pid_exists(pid):
                # ربات crashed
                c.execute('''UPDATE user_bots SET status = ? WHERE id = ?''', ('crashed', bot_id))
                conn.commit()
                print(f"⚠️ ربات {bot_id} crashed شد")
        
        time.sleep(60)  # چک هر دقیقه

if __name__ == "__main__":
    print("🔄 مانیتورینگ ربات‌ها شروع شد...")
    monitor_bots()
