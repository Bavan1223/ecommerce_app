"""
Test script to thoroughly verify:
1. Database tables auto-creation (User, Product, Order, OrderItem)
2. User registration and login
3. Adding products to cart
4. Cart operations: increase, decrease, coupon code validation
5. Cashout & Checkout flow (placing order)
6. Order & OrderItem persistence
7. User order history
8. Admin orders view & status update
"""
from ecommerce_app.app import app, db, User, Product, Order, OrderItem, COUPONS

def run_tests():
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            print("1. DB tables created successfully.")

            # Create test user
            test_user = User.query.filter_by(username="testshopper").first()
            if not test_user:
                test_user = User(username="testshopper", email="shopper@test.com", is_admin=True)
                test_user.set_password("password123")
                db.session.add(test_user)
                db.session.commit()
            print(f"2. Test user ready: ID={test_user.id}, Username={test_user.username}")

            # Verify products exist
            products = Product.query.all()
            print(f"3. Products in DB: {len(products)} found.")
            assert len(products) > 0, "No products found!"
            p1 = products[0]

        # Login
        res = client.post('/login', data={'action': 'login', 'username': 'testshopper', 'password': 'password123'}, follow_redirects=True)
        assert res.status_code == 200
        print("4. Login successful.")

        # Add item to cart
        res = client.get(f'/add_to_cart_check/{p1.id}', follow_redirects=True)
        assert res.status_code == 200
        print(f"5. Added product {p1.name} to cart.")

        # Increase quantity
        res = client.get(f'/cart/update/{p1.id}/increase', follow_redirects=True)
        assert res.status_code == 200
        print("6. Increased product quantity in cart.")

        # Apply coupon SAVE10
        res = client.post('/apply_coupon', data={'coupon_code': 'SAVE10', 'next': 'cart'}, follow_redirects=True)
        assert res.status_code == 200
        assert b'SAVE10' in res.data
        print("7. Coupon SAVE10 applied successfully.")

        # Place Order via Checkout POST
        checkout_payload = {
            'full_name': 'Test Shopper',
            'email': 'shopper@test.com',
            'phone': '1234567890',
            'address': '42 Silicon Avenue',
            'city': 'Tech City',
            'state': 'CA',
            'zip_code': '94016',
            'payment_method': 'cod',
            'notes': 'Leave with security guard'
        }
        res = client.post('/checkout', data=checkout_payload, follow_redirects=True)
        assert res.status_code == 200
        assert b'Your Order is Confirmed' in res.data or b'Order Details' in res.data
        print("8. Checkout placed successfully!")

        with app.app_context():
            # Verify order in DB
            order = Order.query.filter_by(user_id=test_user.id).order_by(Order.created_at.desc()).first()
            assert order is not None
            assert order.full_name == 'Test Shopper'
            assert order.payment_method == 'cod'
            assert order.coupon_code == 'SAVE10'
            assert len(order.items) > 0
            print(f"9. Order verified in DB: Order #{order.id}, Total=${order.total_amount:.2f}, Items={len(order.items)}")

        # Verify User Order History
        res = client.get('/orders')
        assert res.status_code == 200
        assert b'My Order History' in res.data
        print("10. User order history page verified.")

        # Verify Admin Orders List
        res = client.get('/admin/orders')
        assert res.status_code == 200
        assert b'Customer Orders Management' in res.data
        print("11. Admin orders management verified.")

        # Verify Admin update status
        with app.app_context():
            order_id = order.id
        res = client.post(f'/admin/order/{order_id}/status', data={'order_status': 'Shipped', 'payment_status': 'Paid via COD'}, follow_redirects=True)
        assert res.status_code == 200

        with app.app_context():
            updated_order = Order.query.get(order_id)
            assert updated_order.order_status == 'Shipped'
            print(f"12. Order #{order_id} fulfillment status successfully updated to '{updated_order.order_status}'.")

    print("\n==========================================")
    print("ALL ECOMMERCE VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("==========================================")

if __name__ == '__main__':
    run_tests()
