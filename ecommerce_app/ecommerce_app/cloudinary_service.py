"""
Cloudinary Image Storage Module (Free Tier)
- Uploads product images and user profile pictures to Cloudinary
- Completely replaces Firebase Storage (no Blaze requirement)
- Falls back to local static filesystem uploads if credentials are not configured
"""

import os
import uuid
import logging
from typing import Optional, Dict, Any
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

# Check configuration
_is_configured = False

def is_cloudinary_configured() -> bool:
    """Checks if valid Cloudinary credentials are provided in the environment."""
    cloud_name = os.environ.get('CLOUDINARY_CLOUD_NAME')
    api_key = os.environ.get('CLOUDINARY_API_KEY')
    api_secret = os.environ.get('CLOUDINARY_API_SECRET')
    return bool(cloud_name and api_key and api_secret)


def configure_cloudinary():
    """Configures the cloudinary library using environment variables."""
    global _is_configured
    if _is_configured:
        return True

    if is_cloudinary_configured():
        try:
            import cloudinary
            cloudinary.config(
                cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
                api_key=os.environ.get('CLOUDINARY_API_KEY'),
                api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
                secure=True
            )
            _is_configured = True
            logger.info("Cloudinary successfully configured.")
            return True
        except Exception as e:
            logger.warning(f"Failed to configure Cloudinary: {e}")
            return False
    return False


def upload_product_image(file_storage, local_fallback_dir: str = 'static/images') -> Optional[str]:
    """
    Uploads a product image to Cloudinary (folder: 'ecommerce/products').
    If Cloudinary is not configured or fails, falls back gracefully to saving
    in the local fallback directory and returns the local filename.
    """
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None

    # Try Cloudinary upload
    if configure_cloudinary():
        try:
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                file_storage,
                folder="ecommerce/products",
                transformation=[
                    {'width': 600, 'height': 600, 'crop': 'pad', 'background': 'white'}
                ]
            )
            secure_url = result.get('secure_url')
            if secure_url:
                logger.info(f"Product image uploaded to Cloudinary: {secure_url}")
                return secure_url
        except Exception as e:
            logger.warning(f"Cloudinary upload failed ({e}). Falling back to local storage.")
            # Rewind file pointer for fallback save
            try:
                file_storage.seek(0)
            except Exception:
                pass

    # Local fallback
    try:
        os.makedirs(local_fallback_dir, exist_ok=True)
        unique_name = f"prod_{uuid.uuid4().hex[:8]}_{filename}"
        save_path = os.path.join(local_fallback_dir, unique_name)
        file_storage.save(save_path)
        logger.info(f"Saved product image locally to {save_path}")
        return unique_name
    except Exception as e:
        logger.error(f"Failed local fallback image save: {e}")
        return None


def upload_profile_image(file_storage, local_fallback_dir: str = 'static/uploads') -> Optional[str]:
    """
    Uploads a user avatar to Cloudinary (folder: 'ecommerce/profiles').
    Falls back gracefully to local storage if Cloudinary is not configured.
    """
    if not file_storage or not getattr(file_storage, 'filename', None):
        return None

    filename = secure_filename(file_storage.filename)
    if not filename:
        return None

    if configure_cloudinary():
        try:
            import cloudinary.uploader
            result = cloudinary.uploader.upload(
                file_storage,
                folder="ecommerce/profiles",
                transformation=[
                    {'width': 300, 'height': 300, 'crop': 'thumb', 'gravity': 'face'}
                ]
            )
            secure_url = result.get('secure_url')
            if secure_url:
                logger.info(f"Profile image uploaded to Cloudinary: {secure_url}")
                return secure_url
        except Exception as e:
            logger.warning(f"Cloudinary profile upload failed ({e}). Falling back to local storage.")
            try:
                file_storage.seek(0)
            except Exception:
                pass

    # Local fallback
    try:
        os.makedirs(local_fallback_dir, exist_ok=True)
        unique_name = f"user_{uuid.uuid4().hex[:8]}_{filename}"
        save_path = os.path.join(local_fallback_dir, unique_name)
        file_storage.save(save_path)
        logger.info(f"Saved profile image locally to {save_path}")
        return unique_name
    except Exception as e:
        logger.error(f"Failed local fallback profile save: {e}")
        return None


def delete_image(public_id_or_url: str) -> bool:
    """Deletes an image from Cloudinary by public ID if configured."""
    if not public_id_or_url or not configure_cloudinary():
        return False
    try:
        import cloudinary.uploader
        # Extract public_id if full URL was provided
        public_id = public_id_or_url
        if 'res.cloudinary.com' in public_id_or_url:
            parts = public_id_or_url.split('/upload/')
            if len(parts) > 1:
                sub = parts[1].split('/', 1)
                if len(sub) > 1:
                    public_id = sub[1].rsplit('.', 1)[0]
        cloudinary.uploader.destroy(public_id)
        return True
    except Exception as e:
        logger.warning(f"Cloudinary delete failed: {e}")
        return False
