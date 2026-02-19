import telebot
from telebot import types
import sqlite3
import json
import os
import subprocess
import sys
import time
from datetime import datetime

TOKEN = "توکن_ربات_تو"
bot = telebot.TeleBot(TOKEN)

# ==================== دیتابیس ====================
conn = sqlite3.connect('bot_builder.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, token TEXT, step TEXT, temp_data TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS user_bots
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER,
              bot_token TEXT,
              bot_name TEXT,
              config TEXT)''')
conn.commit()

# ==================== مرحله 1: دریافت توکن ====================
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    c.execute('INSERT OR REPLACE INTO users (user_id, step) VALUES (?, ?)', (user_id, 'waiting_token'))
    conn.commit()
    
    bot.send_message(
        user_id,
        "🤖 **به ربات ساز خوش آمدید!**\n\n"
        "لطفاً توکن ربات خود را از @BotFather بگیرید و اینجا بفرستید:"
    )

# ==================== مرحله 2: دریافت توکن ====================
@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.from_user.id
    c.execute('SELECT step, temp_data FROM users WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    
    if not result:
        start(message)
        return
    
    step, temp_data = result
    temp = json.loads(temp_data) if temp_data else {}
    
    if step == 'waiting_token':
        token = message.text.strip()
        temp['token'] = token
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_text', json.dumps(temp), user_id))
        conn.commit()
        
        bot.send_message(
            user_id,
            "✅ توکن ذخیره شد!\n\n"
            "✍️ **متن خوش‌آمدگویی رباتت رو بنویس:**"
        )
    
    elif step == 'waiting_text':
        welcome_text = message.text
        temp['welcome_text'] = welcome_text
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_button_type', json.dumps(temp), user_id))
        conn.commit()
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("🔘 دکمه درون خطی", callback_data="btn_inline")
        btn2 = types.InlineKeyboardButton("📋 دکمه متنی", callback_data="btn_keyboard")
        markup.add(btn1, btn2)
        
        bot.send_message(
            user_id,
            "🎯 **چه نوع دکمه‌ای می‌خوای؟**",
            reply_markup=markup
        )

# ==================== مرحله 3: انتخاب نوع دکمه ====================
@bot.callback_query_handler(func=lambda call: call.data in ['btn_inline', 'btn_keyboard'])
def button_type(call):
    user_id = call.from_user.id
    c.execute('SELECT temp_data FROM users WHERE user_id = ?', (user_id,))
    temp = json.loads(c.fetchone()[0])
    
    temp['button_type'] = call.data
    c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
              ('waiting_button_name', json.dumps(temp), user_id))
    conn.commit()
    
    bot.edit_message_text(
        "✍️ **اسم دکمه رو بنویس:**\n(مثال: 🛍 محصولات)",
        user_id,
        call.message.message_id
    )

# ==================== مرحله 4: دریافت اسم دکمه ====================
@bot.message_handler(func=lambda m: True)
def get_button_name(message):
    user_id = message.from_user.id
    c.execute('SELECT step, temp_data FROM users WHERE user_id = ?', (user_id,))
    step, temp_data = c.fetchone()
    temp = json.loads(temp_data)
    
    if step == 'waiting_button_name':
        temp['button_name'] = message.text
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_button_action', json.dumps(temp), user_id))
        conn.commit()
        
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("💻 با کدنویسی", callback_data="action_code")
        btn2 = types.InlineKeyboardButton("🔄 لینک خارجی", callback_data="action_url")
        btn3 = types.InlineKeyboardButton("📞 پشتیبانی", callback_data="action_support")
        btn4 = types.InlineKeyboardButton("🔙 بازگشت", callback_data="action_back")
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(
            user_id,
            f"🔘 دکمه '{message.text}'\n\n"
            f"**این دکمه چه کاری انجام بده؟**",
            reply_markup=markup
        )

# ==================== مرحله 5: انتخاب نوع عملکرد ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('action_'))
def button_action(call):
    user_id = call.from_user.id
    action = call.data.replace('action_', '')
    
    c.execute('SELECT temp_data FROM users WHERE user_id = ?', (user_id,))
    temp = json.loads(c.fetchone()[0])
    
    if action == 'code':
        temp['action_type'] = 'code'
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_code_file', json.dumps(temp), user_id))
        conn.commit()
        
        bot.edit_message_text(
            "📁 **فایل پایتون خود را با نام m.py آپلود کنید.**\n\n"
            "⚠️ دقت کنید:\n"
            "• حتماً نام فایل m.py باشد\n"
            "• کد شما باید با کتابخانه pyTelegramBotAPI نوشته شده باشد\n"
            "• تابع main باید داشته باشد\n\n"
            "📤 فایل را آپلود کنید:",
            user_id,
            call.message.message_id
        )
    
    elif action == 'url':
        temp['action_type'] = 'url'
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_url', json.dumps(temp), user_id))
        conn.commit()
        
        bot.edit_message_text(
            "🔗 **لینک مورد نظر را وارد کنید:**\n(مثال: https://t.me/mychannel)",
            user_id,
            call.message.message_id
        )
    
    elif action == 'support':
        temp['action_type'] = 'support'
        temp['support_id'] = '@support_bot'
        save_bot_config(user_id, temp)
        
        bot.edit_message_text(
            "✅ **تنظیمات پشتیبانی ذخیره شد!**\n"
            "ربات شما در حال ساخته شدن است...",
            user_id,
            call.message.message_id
        )
        generate_bot(user_id, temp)

# ==================== مرحله 6: دریافت فایل کد ====================
@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    c.execute('SELECT step, temp_data FROM users WHERE user_id = ?', (user_id,))
    step, temp_data = c.fetchone()
    
    if step != 'waiting_code_file':
        return
    
    file_info = bot.get_file(message.document.file_id)
    
    if message.document.file_name != 'm.py':
        bot.send_message(user_id, "❌ نام فایل باید m.py باشد!")
        return
    
    downloaded_file = bot.download_file(file_info.file_path)
    
    # ذخیره فایل
    os.makedirs(f'user_files/{user_id}', exist_ok=True)
    file_path = f'user_files/{user_id}/m.py'
    with open(file_path, 'wb') as f:
        f.write(downloaded_file)
    
    # بررسی کتابخانه‌های مورد نیاز
    with open(file_path, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # تشخیص کتابخانه‌های مورد نیاز
    imports = []
    for line in code.split('\n'):
        if line.startswith('import ') or line.startswith('from '):
            lib = line.split()[1].split('.')[0]
            if lib not in ['telebot', 'os', 'sys', 'json', 'sqlite3']:
                imports.append(lib)
    
    temp = json.loads(temp_data)
    temp['code_file'] = file_path
    temp['imports'] = list(set(imports))
    
    if imports:
        # نمایش کتابخانه‌های پیشنهادی
        markup = types.InlineKeyboardMarkup(row_width=2)
        for lib in imports[:10]:
            btn = types.InlineKeyboardButton(f"📦 {lib}", callback_data=f"install_{lib}")
            markup.add(btn)
        btn_skip = types.InlineKeyboardButton("⏭ رد کردن", callback_data="install_skip")
        markup.add(btn_skip)
        
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_install', json.dumps(temp), user_id))
        conn.commit()
        
        bot.send_message(
            user_id,
            f"📦 **کتابخانه‌های مورد نیاز شناسایی شد:**\n{', '.join(imports)}\n\n"
            f"کدوم رو نصب کنم؟",
            reply_markup=markup
        )
    else:
        # اجرای مستقیم کد
        run_user_code(user_id, temp)
        generate_bot(user_id, temp)

# ==================== مرحله 7: نصب کتابخانه ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('install_'))
def install_library(call):
    user_id = call.from_user.id
    lib = call.data.replace('install_', '')
    
    if lib == 'skip':
        bot.edit_message_text("⏭ نصب کتابخانه رد شد.", user_id, call.message.message_id)
    else:
        bot.edit_message_text(f"📦 در حال نصب {lib}...", user_id, call.message.message_id)
        
        # نصب کتابخانه
        subprocess.run([sys.executable, '-m', 'pip', 'install', lib])
        
        bot.send_message(user_id, f"✅ {lib} نصب شد!")
    
    # اجرای کد
    c.execute('SELECT temp_data FROM users WHERE user_id = ?', (user_id,))
    temp = json.loads(c.fetchone()[0])
    run_user_code(user_id, temp)
    generate_bot(user_id, temp)

# ==================== اجرای کد کاربر ====================
def run_user_code(user_id, temp):
    try:
        # اجرای کد در محیط ایزوله
        result = subprocess.run(
            [sys.executable, temp['code_file']],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            bot.send_message(user_id, f"✅ کد با موفقیت اجرا شد!\n{result.stdout}")
        else:
            bot.send_message(user_id, f"❌ خطا در اجرا:\n{result.stderr}")
            
    except Exception as e:
        bot.send_message(user_id, f"❌ خطا: {str(e)}")

# ==================== ساخت ربات نهایی ====================
def generate_bot(user_id, config):
    # دریافت تنظیمات بیشتر
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn1 = types.InlineKeyboardButton("👥 آمار کاربران", callback_data="feature_stats")
    btn2 = types.InlineKeyboardButton("📢 پیام همگانی", callback_data="feature_broadcast")
    btn3 = types.InlineKeyboardButton("💰 درگاه پرداخت", callback_data="feature_payment")
    btn4 = types.InlineKeyboardButton("📦 مدیریت محصولات", callback_data="feature_products")
    btn5 = types.InlineKeyboardButton("✅ تایید و ساخت", callback_data="feature_done")
    markup.add(btn1, btn2, btn3, btn4, btn5)
    
    c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
              ('waiting_features', json.dumps(config), user_id))
    conn.commit()
    
    bot.send_message(
        user_id,
        "✨ **قابلیت‌های اضافی:**\n\n"
        "کدوم رو می‌خوای به رباتت اضافه کنی؟",
        reply_markup=markup
    )

# ==================== انتخاب قابلیت‌ها ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith('feature_'))
def add_features(call):
    user_id = call.from_user.id
    feature = call.data.replace('feature_', '')
    
    c.execute('SELECT temp_data FROM users WHERE user_id = ?', (user_id,))
    temp = json.loads(c.fetchone()[0])
    
    if 'features' not in temp:
        temp['features'] = []
    
    if feature == 'stats':
        temp['features'].append('stats')
        bot.answer_callback_query(call.id, "✅ آمار کاربران اضافه شد!")
        
    elif feature == 'broadcast':
        temp['features'].append('broadcast')
        bot.answer_callback_query(call.id, "✅ پیام همگانی اضافه شد!")
        
    elif feature == 'payment':
        temp['features'].append('payment')
        bot.edit_message_text(
            "💰 **لینک درگاه پرداخت خود را وارد کنید:**\n"
            "(مثال: https://zarinpal.com/merchant)",
            user_id,
            call.message.message_id
        )
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_payment_link', json.dumps(temp), user_id))
        conn.commit()
        return
        
    elif feature == 'products':
        temp['features'].append('products')
        bot.answer_callback_query(call.id, "✅ مدیریت محصولات اضافه شد!")
        
    elif feature == 'done':
        # ساخت ربات نهایی
        final_bot_code = generate_final_bot_code(temp)
        
        # ذخیره در دیتابیس
        bot_token = temp['token']
        c.execute('''INSERT INTO user_bots (user_id, bot_token, bot_name, config)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, bot_token, f"bot_{user_id}", json.dumps(temp)))
        conn.commit()
        
        bot.edit_message_text(
            "🎉 **ربات شما با موفقیت ساخته شد!**\n\n"
            f"🔑 توکن: `{bot_token}`\n\n"
            f"ربات شما هم اکنون فعال است!\n"
            f"برای شروع به ربات خود بروید: https://t.me/YourBot",
            user_id,
            call.message.message_id,
            parse_mode="Markdown"
        )
        return
    
    c.execute('UPDATE users SET temp_data = ? WHERE user_id = ?',
              (json.dumps(temp), user_id))
    conn.commit()

# ==================== دریافت لینک درگاه ====================
@bot.message_handler(func=lambda m: True)
def get_payment_link(message):
    user_id = message.from_user.id
    c.execute('SELECT step, temp_data FROM users WHERE user_id = ?', (user_id,))
    step, temp_data = c.fetchone()
    
    if step == 'waiting_payment_link':
        temp = json.loads(temp_data)
        temp['payment_link'] = message.text
        temp['features'].append('payment')
        
        c.execute('UPDATE users SET step = ?, temp_data = ? WHERE user_id = ?',
                  ('waiting_features', json.dumps(temp), user_id))
        conn.commit()
        
        # برگشت به منوی قابلیت‌ها
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn1 = types.InlineKeyboardButton("👥 آمار", callback_data="feature_stats")
        btn2 = types.InlineKeyboardButton("📢 پیام همگانی", callback_data="feature_broadcast")
        btn3 = types.InlineKeyboardButton("📦 محصولات", callback_data="feature_products")
        btn4 = types.InlineKeyboardButton("✅ تایید", callback_data="feature_done")
        markup.add(btn1, btn2, btn3, btn4)
        
        bot.send_message(
            user_id,
            "✅ لینک درگاه ذخیره شد!\n\n"
            "**قابلیت‌های بیشتر:**",
            reply_markup=markup
        )

# ==================== تولید کد نهایی ====================
def generate_final_bot_code(config):
    token = config['token']
    welcome = config.get('welcome_text', 'سلام!')
    button_type = config.get('button_type', 'btn_inline')
    button_name = config.get('button_name', 'دکمه')
    features = config.get('features', [])
    
    code = f'''import telebot
from telebot import types
import sqlite3
import json

bot = telebot.TeleBot("{token}")

# ==================== دیتابیس ====================
conn = sqlite3.connect('bot.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users
             (user_id INTEGER PRIMARY KEY, joined_date TEXT)''')
conn.commit()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    # ثبت کاربر
    c.execute('INSERT OR IGNORE INTO users (user_id, joined_date) VALUES (?, ?)',
              (user_id, datetime.now().isoformat()))
    conn.commit()
    
'''

    # اضافه کردن دکمه
    if button_type == 'btn_inline':
        code += f'''
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("{button_name}", callback_data="button_click")
    markup.add(btn)
    bot.send_message(user_id, "{welcome}", reply_markup=markup)
'''
    else:
        code += f'''
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton("{button_name}")
    markup.add(btn)
    bot.send_message(user_id, "{welcome}", reply_markup=markup)
'''
    
    # اضافه کردن قابلیت‌ها
    if 'stats' in features:
        code += '''
@bot.message_handler(commands=['stats'])
def stats(message):
    c.execute('SELECT COUNT(*) FROM users')
    count = c.fetchone()[0]
    bot.reply_to(message, f"👥 تعداد کاربران: {count}")
'''
    
    if 'broadcast' in features:
        code += '''
@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != ADMIN_ID:
        return
    msg = message.text.replace('/broadcast', '').strip()
    c.execute('SELECT user_id FROM users')
    users = c.fetchall()
    for user in users:
        try:
            bot.send_message(user[0], msg)
        except:
            pass
    bot.reply_to(message, f"✅ پیام به {len(users)} کاربر ارسال شد")
'''
    
    if 'payment' in features:
        payment_link = config.get('payment_link', '#')
        code += f'''
@bot.callback_query_handler(func=lambda call: call.data == "pay")
def pay(call):
    bot.send_message(
        call.message.chat.id,
        "💰 لینک پرداخت:\\n{payment_link}"
    )
'''
    
    if 'products' in features:
        code += '''
# ==================== مدیریت محصولات ====================
c.execute('''CREATE TABLE IF NOT EXISTS products
             (id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT,
              price INTEGER,
              description TEXT)''')
conn.commit()

@bot.message_handler(commands=['add_product'])
def add_product(message):
    msg = bot.reply_to(message, "اسم محصول رو بنویس:")
    bot.register_next_step_handler(msg, get_product_name)

def get_product_name(message):
    name = message.text
    msg = bot.reply_to(message, "قیمت محصول رو بنویس:")
    bot.register_next_step_handler(msg, get_product_price, name)

def get_product_price(message, name):
    price = message.text
    c.execute('INSERT INTO products (name, price) VALUES (?, ?)', (name, price))
    conn.commit()
    bot.reply_to(message, f"✅ محصول {name} با قیمت {price} اضافه شد!")

@bot.message_handler(commands=['products'])
def show_products(message):
    c.execute('SELECT name, price FROM products')
    products = c.fetchall()
    text = "📦 **محصولات:**\\n"
    for p in products:
        text += f"\\n🔸 {p[0]} - {p[1]} تومان"
    bot.reply_to(message, text)
'''
    
    code += '''
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    bot.answer_callback_query(call.id, "دکمه clicked شد!")

bot.infinity_polling()
'''
    
    return code

# ==================== اجرا ====================
if __name__ == "__main__":
    print("🤖 ربات ساز پیشرفته روشن شد...")
    bot.infinity_polling()
