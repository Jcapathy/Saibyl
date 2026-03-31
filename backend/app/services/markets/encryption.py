# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# encrypt_key(plaintext: str) -> str
# decrypt_key(ciphertext: str) -> str
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.core.config import settings

_SALT = b"saibyl-market-key-encryption"


def _get_encryption_key() -> bytes:
    """Derive AES-256 key from SECRET_KEY using PBKDF2."""
    secret = os.environ.get("MARKET_KEY_ENCRYPTION_SECRET", settings.secret_key)
    if not secret or len(secret) < 16:
        raise RuntimeError(
            "MARKET_KEY_ENCRYPTION_SECRET or SECRET_KEY must be set (min 16 chars)"
        )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=100_000,
    )
    return kdf.derive(secret.encode())


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
