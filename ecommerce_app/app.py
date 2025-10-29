from flask import Flask, render_template, request, redirect, url_for, session, flash
import json

app = Flask(__name__)
app.secret_key = 'your_super_secret_key_here'
DEFAULT_PORT = 5001

# --- Product Data ---
PRODUCTS_DICT = {
    1: {'id': 1, 'name': 'Wireless Headphones', 'price': 49.99, 'description': 'High-fidelity audio with active noise cancellation.', 'image_url': 'wirelessheadphone.jpeg'},
    2: {'id': 2, 'name': 'Smart Watch X5', 'price': 199.00, 'description': 'Track your fitness, notifications, and sleep.', 'image_url': 'watch.jpg'},
    3: {'id': 3, 'name': 'Ergonomic Keyboard', 'price': 75.50, 'description': 'Split design for comfortable, all-day typing.', 'image_url': 'keyboard.jpg'},
    4: {'id': 4, 'name': '4K LED Monitor 32"', 'price': 349.99, 'description': 'Stunning clarity for work and gaming.', 'image_url': 'monitor.jpg'},
    5: {'id': 5, 'name': 'Portable Power Bank', 'price': 25.00, 'description': 'Keep your devices charged on the go.', 'image_url': 'powerbank.jpg'},
    6: {'id': 6, 'name': 'Webcam HD 1080p', 'price': 39.99, 'description': 'Crystal clear video calls and streaming.', 'image_url': 'webcam.jpg'}
}
products_list = list(PRODUCTS_DICT.values())


@app.route('/')
def index():
    return render_template('index.html', products=products_list)


@app.route('/add_to_cart_check/<int:product_id>')
def add_to_cart_check(product_id):
    if 'user_id' not in session:
        flash("Please log in to add items to your cart.", "info")
        return redirect(url_for('login'))

    if product_id not in PRODUCTS_DICT:
        flash("Invalid product ID.", "error")
        return redirect(url_for('index'))

    product_key = str(product_id)

    if 'cart' not in session:
        session['cart'] = {}

    current_quantity = session['cart'].get(product_key, 0)
    session['cart'][product_key] = current_quantity + 1
    session.modified = True

    product_name = PRODUCTS_DICT[product_id]['name']
    flash(f"'{product_name}' added to cart!", "success")
    return redirect(url_for('index'))


@app.route('/remove_from_cart/<int:product_id>')
def remove_from_cart(product_id):
    """Removes one quantity of the selected item from the cart."""
    if 'cart' not in session or str(product_id) not in session['cart']:
        flash("Item not found in cart.", "error")
        return redirect(url_for('cart'))

    product_key = str(product_id)
    session['cart'][product_key] -= 1

    if session['cart'][product_key] <= 0:
        del session['cart'][product_key]

    session.modified = True

    flash(f"Removed one '{PRODUCTS_DICT[product_id]['name']}' from cart.", "info")
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
        product = PRODUCTS_DICT.get(product_id)

        if product and quantity > 0:
            subtotal = product['price'] * quantity
            cart_items.append({
                'id': product_id,
                'name': product['name'],
                'price': product['price'],
                'quantity': quantity,
                'subtotal': subtotal
            })
            total_price += subtotal

    return render_template('cart.html', cart_items=cart_items, total_price=total_price)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        action = request.form.get('action')
        username = request.form['username']

        if action == 'login':
            if username == 'testuser':
                session['user_id'] = username
                session['user_email'] = username + "@example.com"
                return redirect(url_for('profile'))
            else:
                return render_template('login.html', error="Invalid username. Try 'testuser'.")

        elif action == 'register':
            session['user_id'] = username
            session['user_email'] = request.form['email']
            return redirect(url_for('profile'))

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('user_email', None)
    session.pop('cart', None)
    return redirect(url_for('index'))


@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        flash("Please log in to access profile.", "warning")
        return redirect(url_for('login'))

    # Load or mock user data (replace this with DB query later)
    user = {
        'first_name': 'Bavan',
        'last_name': 'Kumar',
        'gender': 'Male',
        'email': 'sbavankumar2005@gmail.com',
        'mobile': '+917892907448'
    }

    if request.method == 'POST':
        user['first_name'] = request.form.get('first_name')
        user['last_name'] = request.form.get('last_name')
        user['gender'] = request.form.get('gender')
        user['email'] = request.form.get('email')
        user['mobile'] = request.form.get('mobile')
        flash("Profile updated successfully!", "success")

    return render_template('profile.html', user=user)


if __name__ == '__main__':
    app.run(debug=True, port=DEFAULT_PORT)
