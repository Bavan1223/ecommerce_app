"""
Razorpay Payment Gateway Module (Free-First Test Mode Friendly)
- Uses Razorpay TEST MODE for college / personal project demo
- Ready to switch to LIVE mode via environment variable keys (rzp_live_...)
- Creates orders with server-side amount calculation
- Verifies cryptographic payment signatures on the backend
"""

import os
import hmac
import hashlib
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

def is_razorpay_configured() -> bool:
    """Checks if Razorpay Key ID and Secret are provided."""
    key_id = os.environ.get('RAZORPAY_KEY_ID')
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET')
    return bool(key_id and key_secret)


def get_razorpay_client():
    """Initializes and returns a Razorpay client instance if configured."""
    if not is_razorpay_configured():
        return None
    try:
        import razorpay
        client = razorpay.Client(auth=(
            os.environ.get('RAZORPAY_KEY_ID'),
            os.environ.get('RAZORPAY_KEY_SECRET')
        ))
        return client
    except Exception as e:
        logger.error(f"Error creating Razorpay client: {e}")
        return None


def create_razorpay_order(amount: float, currency: str = 'INR', receipt_id: str = '') -> Optional[Dict[str, Any]]:
    """
    Creates an order in Razorpay (amount in paise, e.g. 100.00 -> 10000 paise).
    Returns order details dictionary or None if gateway not configured.
    """
    client = get_razorpay_client()
    if not client:
        logger.info("Razorpay is not configured. Online payment order creation skipped.")
        return None

    try:
        # Amount in paise (integer)
        amount_paise = int(round(amount * 100))
        order_data = {
            'amount': amount_paise,
            'currency': currency,
            'receipt': f"rcpt_{receipt_id}",
            'payment_capture': 1  # Auto capture
        }
        razorpay_order = client.order.create(data=order_data)
        logger.info(f"Razorpay order created: {razorpay_order.get('id')} for {amount_paise} paise")
        return razorpay_order
    except Exception as e:
        logger.error(f"Failed to create Razorpay order: {e}")
        return None


def verify_payment_signature(razorpay_order_id: str, razorpay_payment_id: str, razorpay_signature: str) -> bool:
    """
    Cryptographically verifies the HMAC SHA256 signature returned by Razorpay Checkout.
    NEVER trusts client-reported payment success without server-side verification.
    """
    key_secret = os.environ.get('RAZORPAY_KEY_SECRET', '')
    if not key_secret or not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
        return False

    try:
        # Expected signature: HMAC SHA256 of (order_id + "|" + payment_id) with key_secret
        msg = f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8')
        generated_signature = hmac.new(
            key_secret.encode('utf-8'),
            msg,
            hashlib.sha256
        ).hexdigest()

        # Constant time comparison to prevent timing attacks
        return hmac.compare_digest(generated_signature, razorpay_signature)
    except Exception as e:
        logger.error(f"Error verifying Razorpay signature: {e}")
        return False
