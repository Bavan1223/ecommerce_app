from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json
from functools import wraps # For our @admin_required decorator
import os  # <-- For file paths
from werkzeug.utils import secure_filename # <-- For secure file uploads
try:
    from ecommerce_app import firebase_service, cloudinary_service
except ImportError:
    import firebase_service
    import cloudinary_service

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'
DEFAULT_PORT = 5001

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database Configuration ---
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # On Render, the free Postgres DB might require this SSL setting
    if "postgres://" in database_url:
         database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # This will run on your local PC
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///store.db'

# Initialize db ONCE, after the config
db = SQLAlchemy(app) 

# --- Product Data (For one-time DB population) ---
# This must be defined *before* the auto-create logic
PRODUCTS_DICT = {
    1: {'id': 1, 'name': 'Wireless Headphones', 'price': 49.99, 'description': 'High-fidelity audio with active noise cancellation.', 'image_url': 'wirelessheadphone.jpeg'},
    2: {'id': 2, 'name': 'Smart Watch X5', 'price': 199.00, 'description': 'Track your fitness, notifications, and sleep.', 'image_url': 'watch.jpg'},
    3: {'id': 3, 'name': 'Ergonomic Keyboard', 'price': 75.50, 'description': 'Split design for comfortable, all-day typing.', 'image_url': 'keyboard.jpg'},
    4: {'id': 4, 'name': '4K LED Monitor 32"', 'price': 349.99, 'description': 'Stunning clarity for work and gaming.', 'image_url': 'monitor.jpg'},
    5: {'id': 5, 'name': 'Portable Power Bank', 'price': 25.00, 'description': 'Keep your devices charged on the go.', 'image_url': 'powerbank.jpg'},
    6: {'id': 6, 'name': 'Webcam HD 1080p', 'price': 39.99, 'description': 'Crystal clear video calls and streaming.', 'image_url': 'webcam.jpg'}
}


# =================================================================
# --- DATABASE MODELS ---
# =================================================================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    gender = db.Column(db.String(10), nullable=True) 
    profile_image = db.Column(db.String(100), nullable=True, default=None)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(100), nullable=False, default='myphoto.png')


from datetime import datetime

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(25), nullable=False)
    address = db.Column(db.String(250), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    zip_code = db.Column(db.String(20), nullable=False)
    subtotal_amount = db.Column(db.Float, nullable=False, default=0.0)
    discount_amount = db.Column(db.Float, nullable=False, default=0.0)
    shipping_fee = db.Column(db.Float, nullable=False, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    coupon_code = db.Column(db.String(50), nullable=True)
    payment_method = db.Column(db.String(50), nullable=False, default='cod')
    payment_status = db.Column(db.String(50), nullable=False, default='Pending')
    order_status = db.Column(db.String(50), nullable=False, default='Processing')
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('orders', lazy=True, cascade="all, delete-orphan"))
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=True)
    product_name = db.Column(db.String(100), nullable=False)
    product_price = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    subtotal = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(100), nullable=True, default='myphoto.png')

    product = db.relationship('Product', backref='order_items', lazy=True)


# --- Supported Coupon Codes ---
COUPONS = {
    'SAVE10': {'code': 'SAVE10', 'discount_percent': 10, 'description': '10% off entire order'},
    'SAVE20': {'code': 'SAVE20', 'discount_percent': 20, 'description': '20% off entire order'},
    'TECHMART50': {'code': 'TECHMART50', 'discount_flat': 50.0, 'description': '$50 flat discount on orders over $150', 'min_spend': 150.0},
    'FREESHIP': {'code': 'FREESHIP', 'free_shipping': True, 'description': 'Free express shipping'}
}


# --- Context Processor to expose cart count and active user to all templates ---
@app.context_processor
def inject_global_vars():
    cart_count = 0
    if 'cart' in session:
        for qty in session['cart'].values():
            try:
                cart_count += int(qty)
            except (ValueError, TypeError):
                pass
    current_user = None
    if 'user_id' in session:
        current_user = User.query.get(session['user_id'])
    return {
        'cart_count': cart_count,
        'current_user': current_user,
        'active_coupons': COUPONS
    }


# --- ✅ NEW: Auto-create and populate tables (Render Free Tier fix) ---
with app.app_context():
    db.create_all()
    
    # --- Auto-populate products if the table is new ---
    if Product.query.first() is None:
        print("Populating products...")
        for prod_id, prod_data in PRODUCTS_DICT.items():
            new_product = Product(
                id=prod_data['id'],
                name=prod_data['name'],
                price=prod_data['price'],
                description=prod_data['description'],
                image_url=prod_data['image_url']
            )
            db.session.add(new_product)
        db.session.commit()
        print("Database initialized and products populated.")
    else:
        print("Database already contains products.")
# -----------------------------------------------------------------


# =================================================================
# --- ADMIN DECORATOR ---
# =================================================================

def admin_required(f):
    """
    Restricts access to routes to only admin users.
    Must be logged in and user.is_admin must be True.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash("You must be logged in to view this page.", "error")
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        
        if not user or not user.is_admin:
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function


# =================================================================
# --- HELPER FUNCTIONS ---
# =================================================================

def allowed_file(filename):
    """Checks if a filename's extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def calculate_cart_totals(cart_data, coupon_code=None):
    """Calculate cart items, subtotal, discount, shipping, and grand total."""
    cart_items = []
    subtotal = 0.0

    for product_id_str, quantity in cart_data.items():
        try:
            product_id = int(product_id_str)
            quantity = int(quantity)
        except (ValueError, TypeError):
            continue

        if quantity <= 0:
            continue

        product = Product.query.get(product_id)
        if product:
            item_subtotal = round(product.price * quantity, 2)
            cart_items.append({
                'id': product.id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'subtotal': item_subtotal,
                'image_url': product.image_url
            })
            subtotal += item_subtotal

    subtotal = round(subtotal, 2)
    shipping_fee = 0.0 if (subtotal >= 100.0 or subtotal == 0) else 9.99
    discount = 0.0

    if coupon_code and coupon_code in COUPONS:
        c = COUPONS[coupon_code]
        if 'min_spend' in c and subtotal < c['min_spend']:
            discount = 0.0
        elif 'discount_percent' in c:
            discount = round(subtotal * (c['discount_percent'] / 100.0), 2)
        elif 'discount_flat' in c:
            discount = round(min(subtotal, c['discount_flat']), 2)
        elif c.get('free_shipping'):
            shipping_fee = 0.0

    total = round(max(0.0, subtotal - discount + shipping_fee), 2)
    return {
        'cart_items': cart_items,
        'subtotal': subtotal,
        'discount': discount,
        'shipping_fee': shipping_fee,
        'total': total,
        'coupon_code': coupon_code
    }


# =================================================================
# --- USER ROUTES ---
# =================================================================

@app.route('/')
def index():
    products = Product.query.all()
    return render_template('index.html', products=products)

@app.route('/add_to_cart_check/<int:product_id>')
def add_to_cart_check(product_id):
    if 'user_id' not in session:
        flash("Please log in to add items to your cart.", "info")
        return redirect(url_for('login'))

    product = Product.query.get(product_id)
    if not product:
        flash("Invalid product ID.", "error")
        return redirect(url_for('index'))

    product_key = str(product_id)
    if 'cart' not in session:
        session['cart'] = {}

    current_quantity = session['cart'].get(product_key, 0)
    session['cart'][product_key] = current_quantity + 1
    session.modified = True

    flash(f"'{product.name}' added to cart!", "success")
    return redirect(url_for('cart'))

@app.route('/cart/update/<int:product_id>/<action>')
def cart_update_quantity(product_id, action):
    if 'user_id' not in session:
        flash("Please log in to modify your cart.", "info")
        return redirect(url_for('login'))

    if 'cart' not in session:
        session['cart'] = {}

    product_key = str(product_id)
    product = Product.query.get(product_id)
    prod_name = product.name if product else "Product"

    if action == 'increase':
        session['cart'][product_key] = session['cart'].get(product_key, 0) + 1
        flash(f"Increased quantity of '{prod_name}'.", "success")
    elif action == 'decrease':
        if product_key in session['cart']:
            session['cart'][product_key] -= 1
            if session['cart'][product_key] <= 0:
                del session['cart'][product_key]
                flash(f"Removed '{prod_name}' from cart.", "info")
            else:
                flash(f"Decreased quantity of '{prod_name}'.", "info")
    elif action == 'delete':
        if product_key in session['cart']:
            del session['cart'][product_key]
            flash(f"Removed '{prod_name}' from cart.", "info")

    session.modified = True
    return redirect(url_for('cart'))

@app.route('/cart/clear')
def cart_clear():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    session['cart'] = {}
    session.pop('applied_coupon', None)
    session.modified = True
    flash("Your shopping cart has been cleared.", "info")
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    return redirect(url_for('cart_update_quantity', product_id=product_id, action='delete'))

@app.route('/apply_coupon', methods=['POST'])
def apply_coupon():
    if 'user_id' not in session:
        flash("Please log in to apply discounts.", "info")
        return redirect(url_for('login'))

    code = request.form.get('coupon_code', '').strip().upper()
    next_page = request.form.get('next', 'cart')

    if not code:
        flash("Please enter a coupon code.", "error")
        return redirect(url_for(next_page))

    if code in COUPONS:
        cart_data = session.get('cart', {})
        totals = calculate_cart_totals(cart_data)
        coupon_data = COUPONS[code]

        if 'min_spend' in coupon_data and totals['subtotal'] < coupon_data['min_spend']:
            flash(f"Coupon '{code}' requires a minimum spend of ${coupon_data['min_spend']:.2f}.", "error")
            return redirect(url_for(next_page))

        session['applied_coupon'] = code
        session.modified = True
        flash(f"Coupon '{code}' applied successfully! {coupon_data['description']}", "success")
    else:
        flash(f"Invalid coupon code '{code}'. Try SAVE10 or SAVE20.", "error")

    return redirect(url_for(next_page))

@app.route('/remove_coupon', methods=['POST'])
def remove_coupon():
    next_page = request.form.get('next', 'cart')
    session.pop('applied_coupon', None)
    session.modified = True
    flash("Coupon removed.", "info")
    return redirect(url_for(next_page))

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        flash("You must be logged in to view your cart.", "info")
        return redirect(url_for('login'))

    cart_data = session.get('cart', {})
    coupon_code = session.get('applied_coupon')
    calc = calculate_cart_totals(cart_data, coupon_code)

    return render_template(
        'cart.html',
        cart_items=calc['cart_items'],
        subtotal=calc['subtotal'],
        discount=calc['discount'],
        shipping_fee=calc['shipping_fee'],
        total_price=calc['total'],
        applied_coupon=coupon_code,
        coupons_list=COUPONS
    )

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        flash("Please log in to proceed to checkout.", "info")
        return redirect(url_for('login'))

    cart_data = session.get('cart', {})
    coupon_code = session.get('applied_coupon')
    calc = calculate_cart_totals(cart_data, coupon_code)

    if not calc['cart_items']:
        flash("Your cart is empty. Add products before checking out.", "info")
        return redirect(url_for('index'))

    user = User.query.get(session['user_id'])

    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        city = request.form.get('city', '').strip()
        state = request.form.get('state', '').strip()
        zip_code = request.form.get('zip_code', '').strip()
        payment_method = request.form.get('payment_method', 'cod')
        notes = request.form.get('notes', '').strip()

        if not all([full_name, email, phone, address, city, state, zip_code]):
            flash("Please fill in all required shipping address fields.", "error")
            return render_template('checkout.html', user=user, calc=calc)

        # Determine payment status
        if payment_method == 'cod':
            payment_status = 'Cash on Delivery'
        elif payment_method == 'upi':
            payment_status = 'Paid via UPI'
        elif payment_method == 'card':
            payment_status = 'Paid via Card'
        else:
            payment_status = 'Pending'

        # Create Order
        new_order = Order(
            user_id=user.id,
            full_name=full_name,
            email=email,
            phone=phone,
            address=address,
            city=city,
            state=state,
            zip_code=zip_code,
            subtotal_amount=calc['subtotal'],
            discount_amount=calc['discount'],
            shipping_fee=calc['shipping_fee'],
            total_amount=calc['total'],
            coupon_code=coupon_code,
            payment_method=payment_method,
            payment_status=payment_status,
            order_status='Processing',
            notes=notes
        )
        db.session.add(new_order)
        db.session.flush() # Populate new_order.id

        # Create Order Items
        for item in calc['cart_items']:
            order_item = OrderItem(
                order_id=new_order.id,
                product_id=item['id'],
                product_name=item['name'],
                product_price=item['price'],
                quantity=item['quantity'],
                subtotal=item['subtotal'],
                image_url=item['image_url']
            )
            db.session.add(order_item)

        db.session.commit()

        # Prepare items for Firestore
        firestore_items = []
        for item in calc['cart_items']:
            firestore_items.append({
                'product_id': item['id'],
                'product_name': item['name'],
                'product_price': item['price'],
                'quantity': item['quantity'],
                'subtotal': item['subtotal'],
                'image_url': item['image_url']
            })

        # Sync order to Firestore
        firebase_service.sync_order_to_firestore({
            'id': new_order.id,
            'user_id': new_order.user_id,
            'full_name': new_order.full_name,
            'email': new_order.email,
            'phone': new_order.phone,
            'address': new_order.address,
            'city': new_order.city,
            'state': new_order.state,
            'zip_code': new_order.zip_code,
            'subtotal_amount': new_order.subtotal_amount,
            'discount_amount': new_order.discount_amount,
            'shipping_fee': new_order.shipping_fee,
            'total_amount': new_order.total_amount,
            'coupon_code': new_order.coupon_code,
            'payment_method': new_order.payment_method,
            'payment_status': new_order.payment_status,
            'order_status': new_order.order_status
        }, firestore_items)

        # Clear cart and applied coupon
        session['cart'] = {}
        session.pop('applied_coupon', None)
        session.modified = True

        flash("🎉 Your order has been placed successfully!", "success")
        return redirect(url_for('order_confirmation', order_id=new_order.id))

    return render_template('checkout.html', user=user, calc=calc)

@app.route('/order/confirmation/<int:order_id>')
def order_confirmation(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    order = Order.query.get_or_404(order_id)
    if order.user_id != session['user_id'] and not session.get('is_admin'):
        flash("You do not have access to this order.", "error")
        return redirect(url_for('index'))

    return render_template('order_confirmation.html', order=order)

@app.route('/orders')
def user_orders():
    if 'user_id' not in session:
        flash("Please log in to view your orders.", "info")
        return redirect(url_for('login'))

    orders = Order.query.filter_by(user_id=session['user_id']).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)

@app.route('/order/<int:order_id>')
def order_details(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    order = Order.query.get_or_404(order_id)
    if order.user_id != session['user_id'] and not session.get('is_admin'):
        flash("You do not have permission to view this order.", "error")
        return redirect(url_for('index'))

    return render_template('order_confirmation.html', order=order, is_detail_view=True)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form.get('username')
        password = request.form.get('password')

        if action == 'login':
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(password):
                session['user_id'] = user.id
                session['user_username'] = user.username
                session['is_admin'] = user.is_admin 
                flash(f"Welcome back, {user.username}!", "success")
                return redirect(url_for('profile'))
            else:
                return render_template('login.html', error="Invalid username or password.")

        elif action == 'register':
            email = request.form.get('email')
            gender = request.form.get('gender') 
            
            if User.query.filter_by(username=username).first():
                return render_template('login.html', error="Username already taken.")
            if User.query.filter_by(email=email).first():
                return render_template('login.html', error="Email already registered.")
            
            new_user = User(username=username, email=email, gender=gender, is_admin=False)
            new_user.set_password(password)
            
            db.session.add(new_user)
            db.session.commit()
            
            # Sync to Firestore
            firebase_service.create_user_firestore({
                'id': new_user.id,
                'username': new_user.username,
                'email': new_user.email,
                'gender': new_user.gender,
                'is_admin': new_user.is_admin,
                'profile_image': new_user.profile_image
            })
            
            session['user_id'] = new_user.id
            session['user_username'] = new_user.username
            session['is_admin'] = new_user.is_admin
            
            flash("Account created successfully! You are now logged in.", "success")
            return redirect(url_for('profile'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_username', None)
    session.pop('cart', None)
    session.pop('is_admin', None) 
    flash("You have been logged out.", "info")
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash("Please log in to access profile.", "info")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    
    if not user:
        session.clear()
        flash("User not found. Please log in again.", "error")
        return redirect(url_for('login'))

    return render_template('profile.html', user=user)

# --- NEW ROUTE FOR EDITING PROFILE ---
@app.route('/profile/edit', methods=['GET', 'POST'])
def profile_edit():
    if 'user_id' not in session:
        flash("Please log in to access this page.", "info")
        return redirect(url_for('login'))

    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        # --- Handle Gender Update ---
        new_gender = request.form.get('gender')
        if new_gender:
            user.gender = new_gender

        # --- Handle File Upload ---
        if 'profile_pic' in request.files:
            file = request.files['profile_pic']
            
            if file.filename != '' and allowed_file(file.filename):
                # Use Cloudinary with local fallback
                uploaded_url = cloudinary_service.upload_profile_image(file, app.config['UPLOAD_FOLDER'])
                if uploaded_url:
                    user.profile_image = uploaded_url
                
            elif file.filename != '' and not allowed_file(file.filename):
                flash('File type not allowed. Please upload .png, .jpg, .jpeg, or .gif', 'error')

        # --- Save changes to DB ---
        db.session.commit()
        
        # Sync to Firestore
        firebase_service.create_user_firestore({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'gender': user.gender,
            'is_admin': user.is_admin,
            'profile_image': user.profile_image
        })

        flash('Profile updated successfully!', 'success')
        return redirect(url_for('profile'))

    # GET request: Show the edit form
    return render_template('profile_edit.html', user=user)


# =================================================================
# --- ADMIN ROUTES ---
# =================================================================

@app.route('/admin')
@admin_required
def admin_dashboard():
    products = Product.query.order_by(Product.id).all()
    return render_template('admin_dashboard.html', products=products)

@app.route('/admin/add', methods=['GET', 'POST'])
@admin_required
def admin_add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        price_str = request.form.get('price')
        description = request.form.get('description')
        image_url = request.form.get('image_url')

        if not name or not price_str:
            flash("Product Name and Price are required.", "error")
            return render_template('admin_form.html', title="Add New Product", product={})

        try:
            price = float(price_str)
        except ValueError:
            flash("Price must be a valid number.", "error")
            return render_template('admin_form.html', title="Add New Product", product={})

        new_product = Product(
            name=name, 
            price=price, 
            description=description, 
            image_url=image_url if image_url else 'myphoto.png'
        )
        db.session.add(new_product)
        db.session.commit()
        
        firebase_service.sync_product_to_firestore({
            'id': new_product.id,
            'name': new_product.name,
            'price': new_product.price,
            'description': new_product.description,
            'image_url': new_product.image_url
        })
        
        flash(f"Product '{name}' added successfully!", "success")
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_form.html', title="Add New Product", product={})

@app.route('/admin/edit/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(product_id):
    product = Product.query.get(product_id)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        product.name = request.form.get('name')
        product.price = float(request.form.get('price'))
        product.description = request.form.get('description')
        product.image_url = request.form.get('image_url')
        
        db.session.commit()

        firebase_service.sync_product_to_firestore({
            'id': product.id,
            'name': product.name,
            'price': product.price,
            'description': product.description,
            'image_url': product.image_url
        })

        flash(f"Product '{product.name}' updated successfully!", "success")
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_form.html', title="Edit Product", product=product)

@app.route('/admin/delete/<int:product_id>')
@admin_required
def admin_delete_product(product_id):
    product = Product.query.get(product_id)
    if product:
        product_name = product.name
        db.session.delete(product)
        db.session.commit()
        flash(f"Product '{product_name}' has been deleted.", "success")
    else:
        flash("Product not found.", "error")
    
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/orders')
@admin_required
def admin_orders():
    status_filter = request.args.get('status')
    query = Order.query.order_by(Order.created_at.desc())
    if status_filter:
        query = query.filter_by(order_status=status_filter)
    orders = query.all()
    return render_template('admin_orders.html', orders=orders, current_filter=status_filter)

@app.route('/admin/order/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_update_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    new_status = request.form.get('order_status')
    payment_status = request.form.get('payment_status')

    if new_status:
        order.order_status = new_status
    if payment_status:
        order.payment_status = payment_status

    db.session.commit()
    flash(f"Order #{order.id} status updated to '{order.order_status}' (Payment: {order.payment_status}).", "success")
    return redirect(url_for('admin_orders'))



# =================================================================
# --- APP STARTUP ---
# =================================================================

if __name__ == '__main__':
    # Get port from environment variable, default to 5001 for local
    port = int(os.environ.get('PORT', DEFAULT_PORT))
    # Run on 0.0.0.0 to be accessible. 
    app.run(debug=False, host='0.0.0.0', port=port)