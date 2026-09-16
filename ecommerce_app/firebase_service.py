"""
Firebase Admin and Firestore Integration Module (Free-Tier Friendly)
- Handles Firebase Authentication (Google & Email/Password token verification)
- Syncs Users, Products, and Orders to Cloud Firestore
- Does NOT use Firebase Cloud Storage (saves costs and Blaze requirement)
- Gracefully handles missing credentials with zero app crashes
"""

import os
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Track status
_firebase_app = None
_firestore_db = None
_is_initialized = False

def initialize_firebase():
    """
    Safely initializes the Firebase Admin SDK using either:
    1. serviceAccountKey.json path (if available locally)
    2. Environment variables (FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY)
    3. Graceful fallback if credentials are absent.
    """
    global _firebase_app, _firestore_db, _is_initialized
    if _is_initialized:
        return _firestore_db

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        # Check if already initialized in default app
        if firebase_admin._apps:
            _firebase_app = firebase_admin.get_app()
            _firestore_db = firestore.client()
            _is_initialized = True
            logger.info("Firebase Admin already initialized.")
            return _firestore_db

        cred = None
        # Check explicit service account json file paths
        possible_paths = [
            os.environ.get('FIREBASE_SERVICE_ACCOUNT_PATH', ''),
            'serviceAccountKey.json',
            os.path.join(os.path.dirname(__file__), 'serviceAccountKey.json'),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'serviceAccountKey.json')
        ]

        for p in possible_paths:
            if p and os.path.exists(p):
                logger.info(f"Found Firebase service account key at: {p}")
                cred = credentials.Certificate(p)
                break

        # Check environment variables if no file found
        if not cred:
            project_id = os.environ.get('FIREBASE_PROJECT_ID')
            client_email = os.environ.get('FIREBASE_CLIENT_EMAIL')
            private_key = os.environ.get('FIREBASE_PRIVATE_KEY')

            if project_id and client_email and private_key:
                # Format newline characters in private key
                formatted_private_key = private_key.replace('\\n', '\n')
                cred = credentials.Certificate({
                    "type": "service_account",
                    "project_id": project_id,
                    "private_key": formatted_private_key,
                    "client_email": client_email,
                    "token_uri": "https://oauth2.googleapis.com/token"
                })
                logger.info("Initialized Firebase credentials from environment variables.")

        if cred:
            _firebase_app = firebase_admin.initialize_app(cred)
            _firestore_db = firestore.client()
            _is_initialized = True
            logger.info("Firebase Admin SDK successfully connected to Firestore.")
        else:
            logger.warning(
                "Firebase credentials not found. Running in Local-Only Fallback Mode. "
                "Add serviceAccountKey.json or set FIREBASE_* env vars to enable Cloud Firestore sync."
            )
    except Exception as e:
        logger.warning(f"Could not initialize Firebase Admin SDK: {e}. Running in Fallback Mode.")

    return _firestore_db


def is_firebase_available() -> bool:
    """Returns True if Firebase Admin is connected and ready."""
    initialize_firebase()
    return _is_initialized and (_firestore_db is not None)


def verify_firebase_token(id_token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a Firebase ID token sent from the client-side Google / Email login.
    Returns decoded token dict with uid, email, name, or None if invalid.
    """
    if not id_token:
        return None

    initialize_firebase()
    if not _is_initialized:
        logger.warning("Firebase verification attempted but Firebase Admin is not configured.")
        return None

    try:
        from firebase_admin import auth
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        logger.error(f"Error verifying Firebase ID token: {e}")
        return None


# =====================================================================
# FIRESTORE CLOUD SYNCHRONIZATION (Free Tier)
# Collections: users, products, orders
# =====================================================================

def create_user_firestore(user_dict: Dict[str, Any]) -> bool:
    """Syncs a user profile to the 'users' collection in Firestore."""
    if not is_firebase_available():
        return False
    try:
        doc_id = str(user_dict.get('id') or user_dict.get('uid'))
        if doc_id:
            _firestore_db.collection('users').document(doc_id).set({
                'username': user_dict.get('username'),
                'email': user_dict.get('email'),
                'gender': user_dict.get('gender'),
                'is_admin': bool(user_dict.get('is_admin')),
                'profile_image': user_dict.get('profile_image'),
                'updated_at': firestore_timestamp()
            }, merge=True)
            return True
    except Exception as e:
        logger.warning(f"Firestore create_user error: {e}")
    return False


def sync_product_to_firestore(product_dict: Dict[str, Any]) -> bool:
    """Syncs a product to the 'products' collection in Firestore."""
    if not is_firebase_available():
        return False
    try:
        doc_id = str(product_dict.get('id'))
        if doc_id:
            _firestore_db.collection('products').document(doc_id).set({
                'id': product_dict.get('id'),
                'name': product_dict.get('name'),
                'price': float(product_dict.get('price', 0.0)),
                'original_price': float(product_dict.get('original_price', 0.0)),
                'discount': int(product_dict.get('discount', 0)),
                'category': product_dict.get('category', 'Electronics'),
                'brand': product_dict.get('brand', 'General'),
                'stock': int(product_dict.get('stock', 10)),
                'description': product_dict.get('description', ''),
                'image_url': product_dict.get('image_url', ''),
                'rating': float(product_dict.get('rating', 4.5)),
                'review_count': int(product_dict.get('review_count', 12)),
                'updated_at': firestore_timestamp()
            }, merge=True)
            return True
    except Exception as e:
        logger.warning(f"Firestore sync_product error: {e}")
    return False


def sync_order_to_firestore(order_dict: Dict[str, Any], items_list: List[Dict[str, Any]]) -> bool:
    """
    Syncs a completed or placed order to the 'orders' collection in Firestore.
    Stores clean JSON data (never binary image data).
    """
    if not is_firebase_available():
        return False
    try:
        order_id = str(order_dict.get('id'))
        if order_id:
            cleaned_items = []
            for item in items_list:
                cleaned_items.append({
                    'product_id': item.get('product_id'),
                    'product_name': item.get('product_name'),
                    'product_price': float(item.get('product_price', 0.0)),
                    'quantity': int(item.get('quantity', 1)),
                    'subtotal': float(item.get('subtotal', 0.0)),
                    'image_url': item.get('image_url', '')
                })

            order_payload = {
                'order_id': order_id,
                'user_id': order_dict.get('user_id'),
                'full_name': order_dict.get('full_name'),
                'email': order_dict.get('email'),
                'phone': order_dict.get('phone'),
                'address': order_dict.get('address'),
                'city': order_dict.get('city'),
                'state': order_dict.get('state'),
                'zip_code': order_dict.get('zip_code'),
                'subtotal': float(order_dict.get('subtotal_amount', 0.0)),
                'discount': float(order_dict.get('discount_amount', 0.0)),
                'shipping_fee': float(order_dict.get('shipping_fee', 0.0)),
                'total_amount': float(order_dict.get('total_amount', 0.0)),
                'coupon_code': order_dict.get('coupon_code', ''),
                'payment_method': order_dict.get('payment_method', 'cod'),
                'payment_status': order_dict.get('payment_status', 'COD_PENDING'),
                'order_status': order_dict.get('order_status', 'PLACED'),
                'razorpay_order_id': order_dict.get('razorpay_order_id', ''),
                'razorpay_payment_id': order_dict.get('razorpay_payment_id', ''),
                'items': cleaned_items,
                'created_at': firestore_timestamp()
            }
            _firestore_db.collection('orders').document(order_id).set(order_payload, merge=True)
            return True
    except Exception as e:
        logger.warning(f"Firestore sync_order error: {e}")
    return False


def get_user_orders_firestore(user_id: int) -> List[Dict[str, Any]]:
    """Retrieves user's orders directly from Firestore if available."""
    if not is_firebase_available():
        return []
    try:
        docs = _firestore_db.collection('orders').where('user_id', '==', user_id).stream()
        results = [doc.to_dict() for doc in docs]
        return sorted(results, key=lambda x: x.get('order_id', 0), reverse=True)
    except Exception as e:
        logger.warning(f"Firestore get_user_orders error: {e}")
        return []


def update_order_firestore(order_id: int, data: Dict[str, Any]) -> bool:
    """Updates order status or payment state in Firestore."""
    if not is_firebase_available():
        return False
    try:
        _firestore_db.collection('orders').document(str(order_id)).update(data)
        return True
    except Exception as e:
        logger.warning(f"Firestore update_order error: {e}")
    return False


def firestore_timestamp():
    """Helper to return current ISO timestamp string."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
