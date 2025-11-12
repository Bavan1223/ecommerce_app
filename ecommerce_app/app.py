from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import json
from functools import wraps # For our @admin_required decorator
import os  # <-- For file paths
from werkzeug.utils import secure_filename # <-- For secure file uploads

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'
DEFAULT_PORT = 5001

# --- File Upload Configuration ---
UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Database Configuration ---
# Get the database URL from the environment variable (Render sets this)
# If it's not set, fall back to the local sqlite database for testing
database_url = os.environ.get('DATABASE_URL')
if database_url:
    # On Render, the free Postgres DB might require this SSL setting
    if "postgres://" in database_url:
         database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # This will run on your local PC
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///store.db'

# --- ✅ THIS IS THE FIX ---
# 'db = SQLAlchemy(app)' is now here ONCE, after the if/else block
db = SQLAlchemy(app)


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

# --- Product Data (For one-time DB population) ---
PRODUCTS_DICT = {
    1: {'id': 1, 'name': 'Wireless Headphones', 'price': 49.99, 'description': 'High-fidelity audio with active noise cancellation.', 'image_url': 'wirelessheadphone.jpeg'},
    2: {'id': 2, 'name': 'Smart Watch X5', 'price': 199.00, 'description': 'Track your fitness, notifications, and sleep.', 'image_url': 'watch.jpg'},
    3: {'id': 3, 'name': 'Ergonomic Keyboard', 'price': 75.50, 'description': 'Split design for comfortable, all-day typing.', 'image_url': 'keyboard.jpg'},
    4: {'id': 4, 'name': '4K LED Monitor 32"', 'price': 349.99, 'description': 'Stunning clarity for work and gaming.', 'image_url': 'monitor.jpg'},
    5: {'id': 5, 'name': 'Portable Power Bank', 'price': 25.00, 'description': 'Keep your devices charged on the go.', 'image_url': 'powerbank.jpg'},
    6: {'id': 6, 'name': 'Webcam HD 1080p', 'price': 39.99, 'description': 'Crystal clear video calls and streaming.', 'image_url': 'webcam.jpg'}
}


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
    return redirect(url_for('index'))

@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    if 'cart' not in session or str(product_id) not in session['cart']:
        flash("Item not found in cart.", "error")
        return redirect(url_for('cart'))

    product_key = str(product_id)
    session['cart'][product_key] -= 1

    if session['cart'][product_key] <= 0:
        del session['cart'][product_key]
    
    session.modified = True
    product = Product.query.get(product_id)
    product_name = product.name if product else "Item"
    
    flash(f"Removed one '{product_name}' from cart.", "info")
    return redirect(url_for('cart'))

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        flash("You must be logged in to view your cart.", "info")
        return redirect(url_for('login'))

    cart_data = session.get('cart', {})
    cart_items = []
    total_price = 0.0

    for product_id_str, quantity in cart_data.items():
        product_id = int(product_id_str)
        product = Product.query.get(product_id)

        if product and quantity > 0:
            subtotal = product.price * quantity
            cart_items.append({
                'id': product_id,
                'name': product.name,
                'price': product.price,
                'quantity': quantity,
                'subtotal': subtotal,
                'image_url': product.image_url
            })
            total_price += subtotal

    return render_template('cart.html', cart_items=cart_items, total_price=total_price)

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
                filename = secure_filename(file.filename)
                unique_filename = f"user_{user.id}_{filename}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                
                file.save(filepath)
                user.profile_image = unique_filename
                
            elif file.filename != '' and not allowed_file(file.filename):
                flash('File type not allowed. Please upload .png, .jpg, .jpeg, or .gif', 'error')

        # --- Save changes to DB ---
        db.session.commit()
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


# =================================================================
# --- DB INIT COMMAND & APP STARTUP ---
# =================================================================

@app.cli.command('init-db')
def init_db_command():
    """Creates the database tables and populates them with initial products."""
    with app.app_context():
        db.create_all()
        
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
            print("Database already initialized.")

if __name__ == '__main__':
    # Get port from environment variable, default to 5001 for local
    port = int(os.environ.get('PORT', DEFAULT_PORT))
    # Run on 0.0.0.0 to be accessible. 
    app.run(debug=False, host='0.0.0.0', port=port)