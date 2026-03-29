# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# encrypt_key(plaintext: str) -> str
# decrypt_key(ciphertext: str) -> str
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _get_encryption_key() -> bytes:
    """Get or derive AES-256 key from env."""
    secret = os.environ.get("MARKET_KEY_ENCRYPTION_SECRET", settings.secret_key)
    # Ensure 32 bytes for AES-256
    key = secret.encode()[:32].ljust(32, b"\0")
    return key


def encrypt_key(plaintext: str) -> str:
    """AES-256-GCM encrypt an API key."""
    key = _get_encryption_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # Store as base64: nonce + ciphertext
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode()


def decrypt_key(encoded: str) -> str:
    """AES-256-GCM decrypt an API key."""
    key = _get_encryption_key()
    combined = base64.b64decode(encoded)
    nonce = combined[:12]
    ciphertext = combined[12:]
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()
