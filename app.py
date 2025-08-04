from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from flask_mail import Mail, Message
import sqlite3
import random
import string
import os
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'your-app-password'  # Replace with your app password
mail = Mail(app)

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 username TEXT UNIQUE,
                 email TEXT UNIQUE,
                 password TEXT,
                 verification_code TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sites (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 user_id INTEGER,
                 site_name TEXT,
                 site_description TEXT,
                 site_link TEXT,
                 site_image TEXT,
                 likes INTEGER DEFAULT 0,
                 FOREIGN KEY (user_id) REFERENCES users (id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS announcements (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 content TEXT,
                 link TEXT,
                 created_at TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# Generate random verification code
def generate_verification_code():
    return ''.join(random.choices(string.digits, k=5))

# Home route
@app.route('/')
def index():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT content, link FROM announcements ORDER BY created_at DESC LIMIT 1')
    announcement = c.fetchone()
    conn.close()
    return render_template('index.html', announcement=announcement)

# Registration route
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        code = generate_verification_code()

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute('INSERT INTO users (username, email, password, verification_code) VALUES (?, ?, ?, ?)',
                      (username, email, password, code))
            conn.commit()
            msg = Message('Verification Code', sender='your-email@gmail.com', recipients=[email])
            msg.body = f'Your verification code is: {code}'
            mail.send(msg)
            conn.close()
            return jsonify({'success': True, 'message': 'Verification code sent to your email!'})
        except sqlite3.IntegrityError:
            conn.close()
            return jsonify({'success': False, 'message': 'Username or email already exists!'})

    return render_template('abt.html')

# Verify code route
@app.route('/verify', methods=['POST'])
def verify():
    email = request.form['email']
    code = request.form['code']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT verification_code FROM users WHERE email = ?', (email,))
    result = c.fetchone()
    if result and result[0] == code:
        c.execute('UPDATE users SET verification_code = NULL WHERE email = ?', (email,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Registration successful!'})
    conn.close()
    return jsonify({'success': False, 'message': 'Invalid code!'})

# Signals route
@app.route('/signals')
def signals():
    try:
        with open('signals.json', 'r') as f:
            signals = json.load(f)
    except:
        signals = [
            {"currency": "BTC/USD", "direction": "Buy", "take_profit": "45000", "stop_loss": "40000"},
            {"currency": "ETH/USD", "direction": "Sell", "take_profit": "3000", "stop_loss": "3500"},
            {"currency": "XRP/USD", "direction": "Buy", "take_profit": "1.2", "stop_loss": "0.8"}
        ]
    return render_template('sig.html', signals=signals)

# Sites route
@app.route('/sites')
def sites():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT id, site_name, site_description, site_link, site_image, likes FROM sites')
    sites = c.fetchall()
    conn.close()
    return render_template('sait.html', sites=sites)

# Like site route
@app.route('/like/<int:site_id>', methods=['POST'])
def like_site(site_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('UPDATE sites SET likes = likes + 1 WHERE id = ?', (site_id,))
    conn.commit()
    c.execute('SELECT likes FROM sites WHERE id = ?', (site_id,))
    likes = c.fetchone()[0]
    conn.close()
    return jsonify({'success': True, 'likes': likes})

# Submit site route
@app.route('/submit_site', methods=['GET', 'POST'])
def submit_site():
    if request.method == 'POST':
        site_name = request.form['site_name']
        site_description = request.form['site_description']
        site_link = request.form['site_link']
        site_image = request.files['site_image']
        user_id = 1  # Replace with actual user ID from session

        # Save image
        image_path = os.path.join('static/uploads', site_image.filename)
        site_image.save(image_path)

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('INSERT INTO sites (user_id, site_name, site_description, site_link, site_image) VALUES (?, ?, ?, ?, ?)',
                  (user_id, site_name, site_description, site_link, image_path))
        conn.commit()

        # Save to m.html
        with open('static/m.html', 'a', encoding='utf-8') as f:
            f.write(f'<div>User ID: {user_id}<br>Site Name: {site_name}<br>Description: {site_description}<br>Link: {site_link}<br>Image: {image_path}<br><br></div>')
        conn.close()
        return jsonify({'success': True, 'message': 'Site submitted successfully!'})

    return render_template('submit_site.html')

# Download Python file
@app.route('/download_python')
def download_python():
    return send_file('moai.py', as_attachment=True)

# Download HTML file
@app.route('/download_html')
def download_html():
    return send_file('git.html', as_attachment=True)

# Admin announcement route (hidden)
@app.route('/admin/announcement', methods=['GET', 'POST'])
def announcement():
    if request.method == 'POST':
        content = request.form['content']
        link = request.form.get('link', '')
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('INSERT INTO announcements (content, link, created_at) VALUES (?, ?, ?)',
                  (content, link, datetime.now()))
        conn.commit()
        conn.close()
        return redirect(url_for('index'))
    return render_template('announcement.html')

# Admin user management route (hidden)
@app.route('/admin/users', methods=['GET', 'POST'])
def manage_users():
    if request.method == 'POST':
        user_id = request.form['user_id']
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('DELETE FROM users WHERE id = ?', (user_id,))
        c.execute('DELETE FROM sites WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return redirect(url_for('manage_users'))
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('SELECT id, username, email FROM users')
    users = c.fetchall()
    conn.close()
    return render_template('manage_users.html', users=users)

if __name__ == '__main__':
    app.run(debug=True)
