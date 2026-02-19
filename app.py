from flask import Flask, render_template, request, redirect, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import jdatetime  # برای تاریخ شمسی

app = Flask(__name__)
app.secret_key = 'professional-accounting-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///accounting.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)

# ==================== مدل‌های دیتابیس ====================

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(200))
    full_name = db.Column(db.String(100))
    company_name = db.Column(db.String(200))
    economic_code = db.Column(db.String(50))
    national_id = db.Column(db.String(50))
    register_number = db.Column(db.String(50))
    address = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Business(db.Model):
    __tablename__ = 'businesses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    name = db.Column(db.String(200))
    type = db.Column(db.String(50))  # company, shop, freelance, etc
    logo = db.Column(db.String(500))
    address = db.Column(db.Text)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    website = db.Column(db.String(200))
    tax_code = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.now)

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'))
    code = db.Column(db.String(20), unique=True)
    full_name = db.Column(db.String(200))
    company_name = db.Column(db.String(200))
    national_id = db.Column(db.String(50))
    economic_code = db.Column(db.String(50))
    phone = db.Column(db.String(20))
    mobile = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    city = db.Column(db.String(50))
    province = db.Column(db.String(50))
    postal_code = db.Column(db.String(20))
    birth_date = db.Column(db.DateTime)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'))
    code = db.Column(db.String(50), unique=True)
    barcode = db.Column(db.String(100))
    name = db.Column(db.String(200))
    category = db.Column(db.String(100))
    unit = db.Column(db.String(20))  # kg, piece, box, etc
    purchase_price = db.Column(db.Float, default=0)
    sale_price = db.Column(db.Float, default=0)
    wholesale_price = db.Column(db.Float, default=0)
    min_stock = db.Column(db.Float, default=0)
    current_stock = db.Column(db.Float, default=0)
    location = db.Column(db.String(100))
    image = db.Column(db.String(500))
    description = db.Column(db.Text)
    tax_rate = db.Column(db.Float, default=9)  # درصد مالیات
    discount_allowed = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'))
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id'))
    invoice_number = db.Column(db.String(50), unique=True)
    invoice_type = db.Column(db.String(20))  # sale, purchase, return
    status = db.Column(db.String(20))  # draft, confirmed, paid, cancelled
    date = db.Column(db.DateTime, default=datetime.now)
    due_date = db.Column(db.DateTime)
    payment_method = db.Column(db.String(50))  # cash, card, check, online
    bank_account = db.Column(db.String(50))
    check_number = db.Column(db.String(50))
    
    # مبالغ
    subtotal = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    tax = db.Column(db.Float, default=0)
    shipping = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    paid = db.Column(db.Float, default=0)
    balance = db.Column(db.Float, default=0)
    
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)

class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))
    product_name = db.Column(db.String(200))
    quantity = db.Column(db.Float, default=1)
    unit = db.Column(db.String(20))
    price = db.Column(db.Float, default=0)
    discount = db.Column(db.Float, default=0)
    tax = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    business_id = db.Column(db.Integer, db.ForeignKey('businesses.id'))
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'))
    transaction_number = db.Column(db.String(50), unique=True)
    type = db.Column(db.String(20))  # income, expense, transfer
    category = db.Column(db.String(50))
    amount = db.Column(db.Float, default=0)
    payment_method = db.Column(db.String(50))
    bank_account = db.Column(db.String(50))
    check_number = db.Column(db.String(50))
    date = db.Column(db.DateTime, default=datetime.now)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.now)

# ایجاد دیتابیس
with app.app_context():
    db.create_all()
    print("✅ دیتابیس حرفه‌ای ایجاد شد")

# ==================== صفحه اصلی ====================
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect('/dashboard')
    return redirect('/login')

@app.route('/login')
def login():
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect('/login')
    
    user = User.query.get(session['user_id'])
    businesses = Business.query.filter_by(user_id=user.id).all()
    
    # آمار کلی
    today = datetime.now().date()
    start_of_month = today.replace(day=1)
    
    today_sales = db.session.query(db.func.sum(Invoice.total))\
        .filter(Invoice.date >= today).scalar() or 0
    
    month_sales = db.session.query(db.func.sum(Invoice.total))\
        .filter(Invoice.date >= start_of_month).scalar() or 0
    
    total_customers = Customer.query.count()
    total_products = Product.query.count()
    
    # آخرین فاکتورها
    recent_invoices = Invoice.query.order_by(Invoice.created_at.desc()).limit(10).all()
    
    return render_template_string(DASHBOARD_TEMPLATE,
        user=user,
        businesses=businesses,
        today_sales=today_sales,
        month_sales=month_sales,
        total_customers=total_customers,
        total_products=total_products,
        recent_invoices=recent_invoices
    )

# ==================== مدیریت فاکتور ====================
@app.route('/invoices')
def invoices():
    if 'user_id' not in session:
        return redirect('/login')
    
    invoices_list = Invoice.query.order_by(Invoice.created_at.desc()).all()
    return render_template_string(INVOICE_TEMPLATE, invoices=invoices_list)

@app.route('/invoice/new', methods=['GET', 'POST'])
def new_invoice():
    if 'user_id' not in session:
        return redirect('/login')
    
    if request.method == 'POST':
        data = request.json
        # ایجاد فاکتور جدید
        last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
        invoice_number = f"INV-{datetime.now().strftime('%Y%m')}-{(last_invoice.id+1 if last_invoice else 1):04d}"
        
        invoice = Invoice(
            business_id=session.get('business_id', 1),
            customer_id=data.get('customer_id'),
            invoice_number=invoice_number,
            invoice_type=data.get('type', 'sale'),
            status='draft',
            due_date=datetime.strptime(data.get('due_date'), '%Y-%m-%d') if data.get('due_date') else None,
            subtotal=data.get('subtotal', 0),
            discount=data.get('discount', 0),
            tax=data.get('tax', 0),
            total=data.get('total', 0),
            description=data.get('description'),
            created_by=session['user_id']
        )
        db.session.add(invoice)
        db.session.commit()
        
        # ثبت آیتم‌ها
        for item in data.get('items', []):
            invoice_item = InvoiceItem(
                invoice_id=invoice.id,
                product_id=item.get('product_id'),
                product_name=item.get('product_name'),
                quantity=item.get('quantity', 1),
                price=item.get('price', 0),
                total=item.get('total', 0)
            )
            db.session.add(invoice_item)
        
        db.session.commit()
        
        return jsonify({'success': True, 'invoice_id': invoice.id, 'number': invoice.invoice_number})
    
    customers = Customer.query.all()
    products = Product.query.all()
    return render_template_string(INVOICE_FORM_TEMPLATE, customers=customers, products=products)

@app.route('/invoice/<int:invoice_id>/pdf')
def invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    items = InvoiceItem.query.filter_by(invoice_id=invoice_id).all()
    
    # ایجاد PDF (با کتابخانه reportlab)
    # اینجا کد تولید PDF رو می‌نویسم
    
    return jsonify({'success': True})

# ==================== مدیریت مشتریان ====================
@app.route('/customers')
def customers():
    if 'user_id' not in session:
        return redirect('/login')
    
    customers_list = Customer.query.all()
    return render_template_string(CUSTOMER_TEMPLATE, customers=customers_list)

@app.route('/customer/new', methods=['POST'])
def new_customer():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    data = request.json
    
    # تولید کد مشتری
    last_customer = Customer.query.order_by(Customer.id.desc()).first()
    customer_code = f"CUS-{(last_customer.id+1 if last_customer else 1):05d}"
    
    customer = Customer(
        business_id=session.get('business_id', 1),
        code=customer_code,
        full_name=data.get('full_name'),
        company_name=data.get('company_name'),
        national_id=data.get('national_id'),
        economic_code=data.get('economic_code'),
        phone=data.get('phone'),
        mobile=data.get('mobile'),
        email=data.get('email'),
        address=data.get('address'),
        city=data.get('city'),
        province=data.get('province'),
        postal_code=data.get('postal_code')
    )
    
    db.session.add(customer)
    db.session.commit()
    
    return jsonify({'success': True, 'customer': {'id': customer.id, 'code': customer.code}})

# ==================== مدیریت محصولات ====================
@app.route('/products')
def products():
    if 'user_id' not in session:
        return redirect('/login')
    
    products_list = Product.query.all()
    return render_template_string(PRODUCT_TEMPLATE, products=products_list)

@app.route('/product/new', methods=['POST'])
def new_product():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    data = request.json
    
    # تولید کد محصول
    last_product = Product.query.order_by(Product.id.desc()).first()
    product_code = f"PRD-{(last_product.id+1 if last_product else 1):05d}"
    
    product = Product(
        business_id=session.get('business_id', 1),
        code=product_code,
        barcode=data.get('barcode'),
        name=data.get('name'),
        category=data.get('category'),
        unit=data.get('unit'),
        purchase_price=data.get('purchase_price', 0),
        sale_price=data.get('sale_price', 0),
        wholesale_price=data.get('wholesale_price', 0),
        min_stock=data.get('min_stock', 0),
        current_stock=data.get('current_stock', 0),
        location=data.get('location'),
        description=data.get('description'),
        tax_rate=data.get('tax_rate', 9)
    )
    
    db.session.add(product)
    db.session.commit()
    
    return jsonify({'success': True, 'product': {'id': product.id, 'code': product.code}})

# ==================== گزارشات ====================
@app.route('/reports')
def reports():
    if 'user_id' not in session:
        return redirect('/login')
    
    return render_template_string(REPORT_TEMPLATE)

@app.route('/api/reports/sales')
def sales_report():
    if 'user_id' not in session:
        return jsonify({'success': False}), 401
    
    period = request.args.get('period', 'month')
    
    if period == 'day':
        start_date = datetime.now().replace(hour=0, minute=0, second=0)
    elif period == 'week':
        start_date = datetime.now() - timedelta(days=7)
    elif period == 'month':
        start_date = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    elif period == 'year':
        start_date = datetime.now().replace(month=1, day=1, hour=0, minute=0, second=0)
    else:
        start_date = datetime.now() - timedelta(days=30)
    
    invoices = Invoice.query.filter(Invoice.date >= start_date, Invoice.status == 'paid').all()
    
    total_sales = sum(i.total for i in invoices)
    total_count = len(invoices)
    avg_sale = total_sales / total_count if total_count > 0 else 0
    
    # فروش به تفکیک روز
    sales_by_day = {}
    for invoice in invoices:
        day = invoice.date.strftime('%Y-%m-%d')
        if day not in sales_by_day:
            sales_by_day[day] = 0
        sales_by_day[day] += invoice.total
    
    # محصولات پرفروش
    popular_products = db.session.query(
        InvoiceItem.product_id,
        Product.name,
        db.func.sum(InvoiceItem.quantity).label('total_quantity'),
        db.func.sum(InvoiceItem.total).label('total_sales')
    ).join(Product).filter(InvoiceItem.invoice_id.in_([i.id for i in invoices]))\
     .group_by(InvoiceItem.product_id).order_by(db.desc('total_sales')).limit(10).all()
    
    return jsonify({
        'success': True,
        'total_sales': total_sales,
        'total_count': total_count,
        'avg_sale': avg_sale,
        'sales_by_day': sales_by_day,
        'popular_products': [
            {'name': p[1], 'quantity': p[2], 'total': p[3]} for p in popular_products
        ]
    })

# ==================== API ====================
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user = User.query.filter_by(username=data['username']).first()
    
    if user and user.check_password(data['password']):
        session['user_id'] = user.id
        session.permanent = True
        user.last_login = datetime.now()
        db.session.commit()
        return jsonify({'success': True, 'user': {'name': user.full_name or user.username}})
    
    return jsonify({'success': False})

@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.json
    
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'success': False, 'message': 'نام کاربری تکراری است'})
    
    if User.query.filter_by(email=data['email']).first():
        return jsonify({'success': False, 'message': 'ایمیل تکراری است'})
    
    user = User(
        username=data['username'],
        email=data['email'],
        phone=data.get('phone'),
        full_name=data.get('full_name'),
        company_name=data.get('company_name')
    )
    user.set_password(data['password'])
    
    db.session.add(user)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect('/login')

# ==================== قالب‌های HTML ====================

LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>حسابدار حرفه‌ای | ورود</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Vazir', 'IRANSans', 'Tahoma', sans-serif;
        }
        
        body {
            min-height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        
        .login-box {
            background: white;
            border-radius: 30px;
            padding: 50px;
            width: 100%;
            max-width: 450px;
            box-shadow: 0 30px 70px rgba(0,0,0,0.3);
            animation: slideUp 0.5s ease;
        }
        
        @keyframes slideUp {
            from { opacity: 0; transform: translateY(30px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .logo {
            text-align: center;
            margin-bottom: 40px;
        }
        
        .logo-icon {
            width: 100px;
            height: 100px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            font-size: 50px;
            line-height: 100px;
            text-align: center;
            border-radius: 30px;
            margin: 0 auto 20px;
            box-shadow: 0 10px 30px rgba(102,126,234,0.3);
        }
        
        h1 {
            color: #333;
            font-size: 28px;
            margin-bottom: 5px;
        }
        
        .subtitle {
            color: #666;
            font-size: 14px;
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 30px;
            background: #f5f5f5;
            padding: 5px;
            border-radius: 15px;
        }
        
        .tab {
            flex: 1;
            padding: 15px;
            text-align: center;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 500;
        }
        
        .tab.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            box-shadow: 0 5px 15px rgba(102,126,234,0.3);
        }
        
        .input-group {
            margin-bottom: 20px;
        }
        
        label {
            display: block;
            margin-bottom: 8px;
            color: #555;
            font-weight: 500;
        }
        
        input {
            width: 100%;
            padding: 15px;
            border: 2px solid #e0e0e0;
            border-radius: 12px;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        input:focus {
            border-color: #667eea;
            outline: none;
            box-shadow: 0 0 0 3px rgba(102,126,234,0.1);
        }
        
        button {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 12px;
            font-size: 18px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-top: 20px;
        }
        
        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102,126,234,0.3);
        }
        
        .error {
            color: #c00;
            margin-top: 15px;
            padding: 12px;
            background: #fee;
            border-radius: 10px;
            display: none;
        }
        
        .features {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-top: 30px;
            padding-top: 30px;
            border-top: 2px solid #f0f0f0;
        }
        
        .feature {
            text-align: center;
        }
        
        .feature-icon {
            font-size: 24px;
            margin-bottom: 5px;
        }
        
        .feature-text {
            font-size: 12px;
            color: #666;
        }
        
        .demo {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 12px;
            margin-top: 20px;
            font-size: 13px;
            color: #555;
            text-align: center;
        }
    </style>
</head>
<body>
    <div class="login-box">
        <div class="logo">
            <div class="logo-icon">💰</div>
            <h1>حسابدار حرفه‌ای</h1>
            <div class="subtitle">مدیریت هوشمند کسب و کار</div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('login')">ورود</div>
            <div class="tab" onclick="showTab('register')">ثبت نام</div>
        </div>
        
        <!-- فرم ورود -->
        <div id="login-form">
            <div class="input-group">
                <label>نام کاربری</label>
                <input type="text" id="login-username" placeholder="example" value="admin">
            </div>
            <div class="input-group">
                <label>رمز عبور</label>
                <input type="password" id="login-password" placeholder="••••••" value="admin123">
            </div>
            <button onclick="login()">ورود به پنل</button>
        </div>
        
        <!-- فرم ثبت نام -->
        <div id="register-form" style="display:none;">
            <div class="input-group">
                <label>نام و نام خانوادگی</label>
                <input type="text" id="reg-fullname" placeholder="مثال: علی محمدی">
            </div>
            <div class="input-group">
                <label>نام کاربری</label>
                <input type="text" id="reg-username" placeholder="example">
            </div>
            <div class="input-group">
                <label>ایمیل</label>
                <input type="email" id="reg-email" placeholder="info@example.com">
            </div>
            <div class="input-group">
                <label>تلفن</label>
                <input type="text" id="reg-phone" placeholder="09123456789">
            </div>
            <div class="input-group">
                <label>رمز عبور</label>
                <input type="password" id="reg-password" placeholder="••••••">
            </div>
            <button onclick="register()">ثبت نام</button>
        </div>
        
        <div id="errorMsg" class="error"></div>
        
        <div class="features">
            <div class="feature">
                <div class="feature-icon">📊</div>
                <div class="feature-text">گزارشات حرفه‌ای</div>
            </div>
            <div class="feature">
                <div class="feature-icon">📝</div>
                <div class="feature-text">فاکتور آنلاین</div>
            </div>
            <div class="feature">
                <div class="feature-icon">🏪</div>
                <div class="feature-text">مدیریت انبار</div>
            </div>
        </div>
        
        <div class="demo">
            <strong>نسخه دمو:</strong> admin / admin123
        </div>
    </div>
    
    <script>
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            if (tab === 'login') {
                document.querySelector('.tab').classList.add('active');
                document.getElementById('login-form').style.display = 'block';
                document.getElementById('register-form').style.display = 'none';
            } else {
                document.querySelectorAll('.tab')[1].classList.add('active');
                document.getElementById('login-form').style.display = 'none';
                document.getElementById('register-form').style.display = 'block';
            }
        }
        
        async function login() {
            const username = document.getElementById('login-username').value;
            const password = document.getElementById('login-password').value;
            
            if (!username || !password) {
                showError('نام کاربری و رمز را وارد کنید');
                return;
            }
            
            const response = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            
            const data = await response.json();
            
            if (data.success) {
                window.location.href = '/dashboard';
            } else {
                showError('نام کاربری یا رمز اشتباه است');
            }
        }
        
        async function register() {
            const fullname = document.getElementById('reg-fullname').value;
            const username = document.getElementById('reg-username').value;
            const email = document.getElementById('reg-email').value;
            const phone = document.getElementById('reg-phone').value;
            const password = document.getElementById('reg-password').value;
            
            if (!username || !email || !password) {
                showError('فیلدهای ضروری را پر کنید');
                return;
            }
            
            const response = await fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({full_name: fullname, username, email, phone, password})
            });
            
            const data = await response.json();
            
            if (data.success) {
                alert('ثبت نام با موفقیت انجام شد');
                showTab('login');
            } else {
                showError(data.message);
            }
        }
        
        function showError(msg) {
            const errorEl = document.getElementById('errorMsg');
            errorEl.style.display = 'block';
            errorEl.innerHTML = '❌ ' + msg;
        }
    </script>
</body>
</html>
'''

DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>داشبورد | حسابدار حرفه‌ای</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Vazir', 'IRANSans', 'Tahoma', sans-serif;
        }
        
        body {
            background: #f5f7fa;
        }
        
        .header {
            background: white;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1000;
        }
        
        .header-content {
            max-width: 1400px;
            margin: 0 auto;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
        }
        
        .user-menu {
            display: flex;
            align-items: center;
            gap: 20px;
        }
        
        .user-name {
            color: #333;
        }
        
        .logout-btn {
            background: #fee;
            color: #c00;
            padding: 8px 15px;
            border-radius: 8px;
            text-decoration: none;
            font-size: 14px;
        }
        
        .sidebar {
            position: fixed;
            top: 70px;
            right: 0;
            width: 250px;
            bottom: 0;
            background: white;
            box-shadow: -2px 0 10px rgba(0,0,0,0.1);
            padding: 20px;
        }
        
        .menu-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 15px;
            margin: 5px 0;
            border-radius: 10px;
            color: #666;
            text-decoration: none;
            transition: all 0.3s;
        }
        
        .menu-item:hover {
            background: #f5f7fa;
        }
        
        .menu-item.active {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }
        
        .main-content {
            margin-right: 250px;
            margin-top: 70px;
            padding: 30px;
            max-width: 1200px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: white;
            border-radius: 15px;
            padding: 25px;
            box-shadow: 0 5px 20px rgba(0,0,0,0.05);
        }
        
        .stat-card h3 {
            color: #666;
            font-size: 14px;
            margin-bottom: 10px;
        }
        
        .stat-number {
            font-size: 32px;
            font-weight: bold;
            color: #333;
            margin-bottom: 5px;
        }
        
        .stat-label {
            color: #999;
            font-size: 12px;
        }
        
        .chart-container {
            background: white;
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
        }
        
        .recent-invoices {
            background: white;
            border-radius: 15px;
            padding: 25px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            text-align: right;
            padding: 15px;
            background: #f8f9fa;
            color: #666;
            font-weight: 500;
        }
        
        td {
            padding: 15px;
            border-bottom: 1px solid #f0f0f0;
        }
        
        .badge {
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
        }
        
        .badge-success {
            background: #d4edda;
            color: #155724;
        }
        
        .badge-warning {
            background: #fff3cd;
            color: #856404;
        }
        
        .btn {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            text-decoration: none;
            display: inline-block;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <div class="logo">
                <span>💰</span>
                <span>حسابدار حرفه‌ای</span>
            </div>
            <div class="user-menu">
                <span class="user-name">{{ user.full_name or user.username }}</span>
                <a href="/logout" class="logout-btn">🚪 خروج</a>
            </div>
        </div>
    </div>
    
    <div class="sidebar">
        <a href="/dashboard" class="menu-item active">
            <span>📊</span> داشبورد
        </a>
        <a href="/invoices" class="menu-item">
            <span>📝</span> فاکتورها
        </a>
        <a href="/customers" class="menu-item">
            <span>👥</span> مشتریان
        </a>
        <a href="/products" class="menu-item">
            <span>📦</span> محصولات
        </a>
        <a href="/reports" class="menu-item">
            <span>📈</span> گزارشات
        </a>
        <a href="/settings" class="menu-item">
            <span>⚙️</span> تنظیمات
        </a>
    </div>
    
    <div class="main-content">
        <div class="stats-grid">
            <div class="stat-card">
                <h3>فروش امروز</h3>
                <div class="stat-number">{{ '{:,.0f}'.format(today_sales) }}</div>
                <div class="stat-label">تومان</div>
            </div>
            <div class="stat-card">
                <h3>فروش ماه</h3>
                <div class="stat-number">{{ '{:,.0f}'.format(month_sales) }}</div>
                <div class="stat-label">تومان</div>
            </div>
            <div class="stat-card">
                <h3>مشتریان</h3>
                <div class="stat-number">{{ total_customers }}</div>
                <div class="stat-label">نفر</div>
            </div>
            <div class="stat-card">
                <h3>محصولات</h3>
                <div class="stat-number">{{ total_products }}</div>
                <div class="stat-label">قلم</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h3 style="margin-bottom: 20px;">📊 نمودار فروش 30 روز اخیر</h3>
            <canvas id="salesChart" style="height: 300px;"></canvas>
        </div>
        
        <div class="recent-invoices">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <h3>📋 آخرین فاکتورها</h3>
                <a href="/invoice/new" class="btn">+ فاکتور جدید</a>
            </div>
            
            <table>
                <tr>
                    <th>شماره</th>
                    <th>تاریخ</th>
                    <th>مشتری</th>
                    <th>مبلغ</th>
                    <th>وضعیت</th>
                    <th>عملیات</th>
                </tr>
                {% for inv in recent_invoices %}
                <tr>
                    <td>{{ inv.invoice_number }}</td>
                    <td>{{ inv.date.strftime('%Y/%m/%d') }}</td>
                    <td>مشتری {{ inv.customer_id }}</td>
                    <td>{{ '{:,.0f}'.format(inv.total) }}</td>
                    <td>
                        <span class="badge {{ 'badge-success' if inv.status == 'paid' else 'badge-warning' }}">
                            {{ 'پرداخت شده' if inv.status == 'paid' else 'پیش‌نویس' }}
                        </span>
                    </td>
                    <td>
                        <a href="#">👁️</a>
                        <a href="#">🖨️</a>
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        // نمودار فروش
        fetch('/api/reports/sales')
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    const ctx = document.getElementById('salesChart').getContext('2d');
                    new Chart(ctx, {
                        type: 'line',
                        data: {
                            labels: Object.keys(data.sales_by_day),
                            datasets: [{
                                label: 'فروش (تومان)',
                                data: Object.values(data.sales_by_day),
                                borderColor: '#667eea',
                                backgroundColor: 'rgba(102,126,234,0.1)',
                                tension: 0.4
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false
                        }
                    });
                }
            });
    </script>
</body>
</html>
'''

INVOICE_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>فاکتورها</title>
    <style>
        * { font-family: 'Vazir', sans-serif; }
        body { background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; padding: 20px; }
        h1 { color: #667eea; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th { background: #667eea; color: white; padding: 12px; }
        td { padding: 12px; border-bottom: 1px solid #eee; }
        .btn { background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📋 لیست فاکتورها</h1>
        <a href="/invoice/new" class="btn">+ فاکتور جدید</a>
        
        <table>
            <tr>
                <th>شماره</th>
                <th>تاریخ</th>
                <th>مشتری</th>
                <th>مبلغ</th>
                <th>وضعیت</th>
            </tr>
            {% for inv in invoices %}
            <tr>
                <td>{{ inv.invoice_number }}</td>
                <td>{{ inv.date.strftime('%Y/%m/%d') }}</td>
                <td>{{ inv.customer_id }}</td>
                <td>{{ '{:,.0f}'.format(inv.total) }}</td>
                <td>{{ inv.status }}</td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
'''

INVOICE_FORM_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>فاکتور جدید</title>
    <style>
        * { font-family: 'Vazir', sans-serif; }
        body { background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; padding: 30px; }
        h1 { color: #667eea; }
        .form-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 15px 0; }
        input, select { padding: 12px; border: 2px solid #e0e0e0; border-radius: 8px; }
        button { background: #667eea; color: white; padding: 12px 30px; border: none; border-radius: 8px; cursor: pointer; }
        table { width: 100%; margin: 20px 0; }
        th { background: #f5f7fa; padding: 12px; }
        td { padding: 10px; }
        .total-section { text-align: left; font-size: 18px; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>➕ فاکتور جدید</h1>
        
        <div class="form-row">
            <select id="customer">
                <option value="">انتخاب مشتری</option>
                {% for c in customers %}
                <option value="{{ c.id }}">{{ c.full_name or c.company_name }}</option>
                {% endfor %}
            </select>
            <input type="date" id="date" value="{{ datetime.now().strftime('%Y-%m-%d') }}">
            <input type="date" id="dueDate" placeholder="سررسید">
            <select id="type">
                <option value="sale">فروش</option>
                <option value="purchase">خرید</option>
                <option value="return">برگشت</option>
            </select>
        </div>
        
        <h3>آیتم‌ها</h3>
        <table id="items">
            <tr>
                <th>محصول</th>
                <th>تعداد</th>
                <th>قیمت واحد</th>
                <th>تخفیف</th>
                <th>جمع</th>
                <th></th>
            </tr>
            <tr class="item-row">
                <td>
                    <select class="product">
                        <option value="">انتخاب محصول</option>
                        {% for p in products %}
                        <option value="{{ p.id }}" data-price="{{ p.sale_price }}">{{ p.name }}</option>
                        {% endfor %}
                    </select>
                </td>
                <td><input type="number" class="quantity" value="1" min="1"></td>
                <td><input type="number" class="price" value="0"></td>
                <td><input type="number" class="discount" value="0"></td>
                <td class="item-total">0</td>
                <td><button onclick="removeRow(this)">❌</button></td>
            </tr>
        </table>
        
        <button onclick="addRow()">+ افزودن آیتم</button>
        
        <div class="total-section">
            <p>جمع کل: <span id="total">0</span> تومان</p>
            <p>مالیات (9%): <span id="tax">0</span> تومان</p>
            <p><strong>قابل پرداخت: <span id="grandTotal">0</span> تومان</strong></p>
        </div>
        
        <div style="margin-top: 30px;">
            <textarea id="description" placeholder="توضیحات" style="width: 100%; padding: 12px;" rows="3"></textarea>
        </div>
        
        <div style="display: flex; gap: 15px; margin-top: 20px;">
            <button onclick="saveInvoice('draft')">ذخیره به عنوان پیش‌نویس</button>
            <button onclick="saveInvoice('confirmed')" style="background: #00b09b;">تایید و ثبت</button>
        </div>
    </div>
    
    <script>
        function addRow() {
            const table = document.getElementById('items');
            const newRow = table.insertRow();
            newRow.className = 'item-row';
            newRow.innerHTML = `
                <td>
                    <select class="product" onchange="updatePrice(this)">
                        <option value="">انتخاب محصول</option>
                        {% for p in products %}
                        <option value="{{ p.id }}" data-price="{{ p.sale_price }}">{{ p.name }}</option>
                        {% endfor %}
                    </select>
                </td>
                <td><input type="number" class="quantity" value="1" min="1" onchange="calculateRow(this)"></td>
                <td><input type="number" class="price" value="0" onchange="calculateRow(this)"></td>
                <td><input type="number" class="discount" value="0" onchange="calculateRow(this)"></td>
                <td class="item-total">0</td>
                <td><button onclick="removeRow(this)">❌</button></td>
            `;
        }
        
        function removeRow(btn) {
            if (document.querySelectorAll('.item-row').length > 1) {
                btn.closest('tr').remove();
                calculateTotal();
            }
        }
        
        function updatePrice(select) {
            const row = select.closest('tr');
            const price = select.selectedOptions[0]?.dataset.price || 0;
            row.querySelector('.price').value = price;
            calculateRow(row.querySelector('.price'));
        }
        
        function calculateRow(element) {
            const row = element.closest('tr');
            const quantity = parseFloat(row.querySelector('.quantity').value) || 0;
            const price = parseFloat(row.querySelector('.price').value) || 0;
            const discount = parseFloat(row.querySelector('.discount').value) || 0;
            
            const total = (quantity * price) - discount;
            row.querySelector('.item-total').textContent = total.toLocaleString();
            
            calculateTotal();
        }
        
        function calculateTotal() {
            let subtotal = 0;
            document.querySelectorAll('.item-total').forEach(el => {
                subtotal += parseFloat(el.textContent.replace(/,/g, '')) || 0;
            });
            
            const tax = subtotal * 0.09;
            const grandTotal = subtotal + tax;
            
            document.getElementById('total').textContent = subtotal.toLocaleString();
            document.getElementById('tax').textContent = tax.toLocaleString();
            document.getElementById('grandTotal').textContent = grandTotal.toLocaleString();
        }
        
        async function saveInvoice(status) {
            const items = [];
            document.querySelectorAll('.item-row').forEach(row => {
                const productSelect = row.querySelector('.product');
                items.push({
                    product_id: productSelect.value,
                    product_name: productSelect.selectedOptions[0]?.text || '',
                    quantity: row.querySelector('.quantity').value,
                    price: row.querySelector('.price').value,
                    total: row.querySelector('.item-total').textContent.replace(/,/g, '')
                });
            });
            
            const data = {
                customer_id: document.getElementById('customer').value,
                date: document.getElementById('date').value,
                due_date: document.getElementById('dueDate').value,
                type: document.getElementById('type').value,
                status: status,
                subtotal: document.getElementById('total').textContent.replace(/,/g, ''),
                tax: document.getElementById('tax').textContent.replace(/,/g, ''),
                total: document.getElementById('grandTotal').textContent.replace(/,/g, ''),
                description: document.getElementById('description').value,
                items: items
            };
            
            const response = await fetch('/invoice/new', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('فاکتور با شماره ' + result.number + ' ثبت شد');
                window.location.href = '/invoices';
            } else {
                alert('خطا در ثبت فاکتور');
            }
        }
    </script>
</body>
</html>
'''

CUSTOMER_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>مشتریان</title>
    <style>
        * { font-family: 'Vazir', sans-serif; }
        body { background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
        h1 { color: #667eea; }
        .btn { background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; }
        th { background: #667eea; color: white; padding: 12px; }
        td { padding: 12px; border-bottom: 1px solid #eee; }
        .modal { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); justify-content: center; align-items: center; }
        .modal-content { background: white; padding: 30px; border-radius: 15px; width: 90%; max-width: 600px; max-height: 80vh; overflow-y: auto; }
        .form-group { margin-bottom: 15px; }
        input, textarea { width: 100%; padding: 10px; border: 2px solid #e0e0e0; border-radius: 8px; }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>👥 مدیریت مشتریان</h1>
            <button class="btn" onclick="showModal()">+ مشتری جدید</button>
        </div>
        
        <table>
            <tr>
                <th>کد</th>
                <th>نام</th>
                <th>شرکت</th>
                <th>تلفن</th>
                <th>ایمیل</th>
                <th>شهر</th>
                <th>عملیات</th>
            </tr>
            {% for c in customers %}
            <tr>
                <td>{{ c.code }}</td>
                <td>{{ c.full_name }}</td>
                <td>{{ c.company_name }}</td>
                <td>{{ c.mobile or c.phone }}</td>
                <td>{{ c.email }}</td>
                <td>{{ c.city }}</td>
                <td>
                    <button onclick="editCustomer({{ c.id }})">✏️</button>
                    <button onclick="viewInvoices({{ c.id }})">📋</button>
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
    
    <!-- مودال مشتری جدید -->
    <div id="customerModal" class="modal">
        <div class="modal-content">
            <h2 style="margin-bottom: 20px;">➕ مشتری جدید</h2>
            
            <div class="form-row">
                <div class="form-group">
                    <label>نام و نام خانوادگی</label>
                    <input type="text" id="fullName" placeholder="مثال: علی محمدی">
                </div>
                <div class="form-group">
                    <label>نام شرکت</label>
                    <input type="text" id="companyName" placeholder="مثال: شرکت آفتاب">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>کد ملی</label>
                    <input type="text" id="nationalId" placeholder="1234567890">
                </div>
                <div class="form-group">
                    <label>کد اقتصادی</label>
                    <input type="text" id="economicCode" placeholder="123456">
                </div>
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>تلفن ثابت</label>
                    <input type="text" id="phone" placeholder="02112345678">
                </div>
                <div class="form-group">
                    <label>موبایل</label>
                    <input type="text" id="mobile" placeholder="09123456789">
                </div>
            </div>
            
            <div class="form-group">
                <label>ایمیل</label>
                <input type="email" id="email" placeholder="info@example.com">
            </div>
            
            <div class="form-row">
                <div class="form-group">
                    <label>استان</label>
                    <input type="text" id="province" placeholder="تهران">
                </div>
                <div class="form-group">
                    <label>شهر</label>
                    <input type="text" id="city" placeholder="تهران">
                </div>
            </div>
            
            <div class="form-group">
                <label>کد پستی</label>
                <input type="text" id="postalCode" placeholder="1234567890">
            </div>
            
            <div class="form-group">
                <label>آدرس</label>
                <textarea id="address" rows="3" placeholder="آدرس کامل"></textarea>
            </div>
            
            <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                <button onclick="hideModal()" style="background: #999;">انصراف</button>
                <button onclick="saveCustomer()" style="background: #667eea;">ذخیره</button>
            </div>
        </div>
    </div>
    
    <script>
        function showModal() {
            document.getElementById('customerModal').style.display = 'flex';
        }
        
        function hideModal() {
            document.getElementById('customerModal').style.display = 'none';
        }
        
        async function saveCustomer() {
            const data = {
                full_name: document.getElementById('fullName').value,
                company_name: document.getElementById('companyName').value,
                national_id: document.getElementById('nationalId').value,
                economic_code: document.getElementById('economicCode').value,
                phone: document.getElementById('phone').value,
                mobile: document.getElementById('mobile').value,
                email: document.getElementById('email').value,
                province: document.getElementById('province').value,
                city: document.getElementById('city').value,
                postal_code: document.getElementById('postalCode').value,
                address: document.getElementById('address').value
            };
            
            const response = await fetch('/customer/new', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            const result = await response.json();
            
            if (result.success) {
                alert('مشتری با کد ' + result.customer.code + ' ثبت شد');
                location.reload();
            } else {
                alert('خطا در ثبت مشتری');
            }
        }
    </script>
</body>
</html>
'''

PRODUCT_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>محصولات</title>
    <style>
        * { font-family: 'Vazir', sans-serif; }
        body { background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; background: white; border-radius: 15px; padding: 20px; }
        .header { display: flex; justify-content: space-between; align-items: center; }
        h1 { color: #667eea; }
        .btn { background: #667eea; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th { background: #667eea; color: white; padding: 12px; }
        td { padding: 12px; border-bottom: 1px solid #eee; }
        .low-stock { background: #fee; color: #c00; padding: 3px 8px; border-radius: 5px; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📦 مدیریت محصولات</h1>
            <a href="/product/new" class="btn">+ محصول جدید</a>
        </div>
        
        <table>
            <tr>
                <th>کد</th>
                <th>نام محصول</th>
                <th>دسته</th>
                <th>موجودی</th>
                <th>قیمت خرید</th>
                <th>قیمت فروش</th>
                <th>وضعیت</th>
            </tr>
            {% for p in products %}
            <tr>
                <td>{{ p.code }}</td>
                <td>{{ p.name }}</td>
                <td>{{ p.category }}</td>
                <td>{{ p.current_stock }} {{ p.unit }}</td>
                <td>{{ '{:,.0f}'.format(p.purchase_price) }}</td>
                <td>{{ '{:,.0f}'.format(p.sale_price) }}</td>
                <td>
                    {% if p.current_stock <= p.min_stock %}
                    <span class="low-stock">⚠️ کمبود موجودی</span>
                    {% else %}
                    <span style="color: #00b09b;">✓ موجود</span>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </table>
    </div>
</body>
</html>
'''

REPORT_TEMPLATE = '''
<!DOCTYPE html>
<html dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>گزارشات</title>
    <style>
        * { font-family: 'Vazir', sans-serif; }
        body { background: #f5f7fa; padding: 20px; }
        .container { max-width: 1200px; margin: 0 auto; }
        .report-card { background: white; border-radius: 15px; padding: 25px; margin-bottom: 20px; }
        h1 { color: #667eea; }
        .filters { display: flex; gap: 15px; margin: 20px 0; }
        select, input { padding: 10px; border: 2px solid #e0e0e0; border-radius: 8px; }
        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 20px 0; }
        .stat-item { text-align: center; padding: 20px; background: #f8f9fa; border-radius: 10px; }
        .stat-value { font-size: 24px; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; margin-top: 5px; }
        canvas { max-height: 400px; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 گزارشات مالی</h1>
        
        <div class="filters">
            <select id="period" onchange="loadReport()">
                <option value="day">امروز</option>
                <option value="week">هفته اخیر</option>
                <option value="month" selected>ماه جاری</option>
                <option value="year">سال جاری</option>
                <option value="custom">دوره دلخواه</option>
            </select>
            <input type="date" id="startDate" style="display:none;">
            <input type="date" id="endDate" style="display:none;">
        </div>
        
        <div class="report-card">
            <h3>آمار کلی</h3>
            <div class="stats-grid" id="summary">
                <div class="stat-item">
                    <div class="stat-value" id="totalSales">0</div>
                    <div class="stat-label">کل فروش</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="totalCount">0</div>
                    <div class="stat-label">تعداد فاکتور</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" id="avgSale">0</div>
                    <div class="stat-label">میانگین فروش</div>
                </div>
            </div>
        </div>
        
        <div class="report-card">
            <h3>نمودار فروش</h3>
            <canvas id="salesChart"></canvas>
        </div>
        
        <div class="report-card">
            <h3>محصولات پرفروش</h3>
            <table style="width:100%;">
                <thead>
                    <tr>
                        <th>محصول</th>
                        <th>تعداد</th>
                        <th>فروش کل</th>
                    </tr>
                </thead>
                <tbody id="popularProducts"></tbody>
            </table>
        </div>
    </div>
    
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script>
        let salesChart = null;
        
        document.getElementById('period').addEventListener('change', function() {
            const custom = this.value === 'custom';
            document.getElementById('startDate').style.display = custom ? 'inline-block' : 'none';
            document.getElementById('endDate').style.display = custom ? 'inline-block' : 'none';
            loadReport();
        });
        
        async function loadReport() {
            const period = document.getElementById('period').value;
            const response = await fetch(`/api/reports/sales?period=${period}`);
            const data = await response.json();
            
            if (data.success) {
                // آمار کلی
                document.getElementById('totalSales').textContent = data.total_sales.toLocaleString();
                document.getElementById('totalCount').textContent = data.total_count;
                document.getElementById('avgSale').textContent = data.avg_sale.toLocaleString();
                
                // محصولات پرفروش
                const tbody = document.getElementById('popularProducts');
                tbody.innerHTML = '';
                data.popular_products.forEach(p => {
                    tbody.innerHTML += `
                        <tr>
                            <td>${p.name}</td>
                            <td>${p.quantity}</td>
                            <td>${p.total.toLocaleString()}</td>
                        </tr>
                    `;
                });
                
                // نمودار
                if (salesChart) salesChart.destroy();
                
                const ctx = document.getElementById('salesChart').getContext('2d');
                salesChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: Object.keys(data.sales_by_day),
                        datasets: [{
                            label: 'فروش (تومان)',
                            data: Object.values(data.sales_by_day),
                            borderColor: '#667eea',
                            backgroundColor: 'rgba(102,126,234,0.1)',
                            tension: 0.4
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: {
                            legend: { display: false }
                        }
                    }
                });
            }
        }
        
        loadReport();
    </script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
