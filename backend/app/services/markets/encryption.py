# PUBLIC INTERFACE
# ─────────────────────────────────────────────────────────
# encrypt_key(plaintext: str) -> str
# decrypt_key(ciphertext: str) -> str
# ─────────────────────────────────────────────────────────
from __future__ import annotations

import base64
import logging
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

from app.core.config import settings

logger = logging.getLogger(__name__)

_LEGACY_SALT = b"saibyl-market-key-encryption"
_LEGACY_ITERATIONS = 100_000
_SALT_LENGTH = 16
_ITERATIONS = 600_000


def _derive_key(salt: bytes, iterations: int) -> bytes:
    secret = os.environ.get("MARKET_KEY_ENCRYPTION_SECRET", settings.secret_key)
    if not secret or len(secret) < 16:
        raise RuntimeError(
            "MARKET_KEY_ENCRYPTION_SECRET or SECRET_KEY must be set (min 16 chars)"
        )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return kdf.derive(secret.encode())


def encrypt_key(plaintext: str) -> str:
    salt = os.urandom(_SALT_LENGTH)
    key = _derive_key(salt, _ITERATIONS)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    # Store as base64: salt + nonce + ciphertext
    combined = salt + nonce + ciphertext
    return base64.b64encode(combined).decode()


def decrypt_key(encoded: str) -> str:
    combined = base64.b64decode(encoded)
    # New format: 16-byte salt + 12-byte nonce + ciphertext
    try:
        salt = combined[:_SALT_LENGTH]
        nonce = combined[_SALT_LENGTH:_SALT_LENGTH + 12]
        ciphertext = combined[_SALT_LENGTH + 12:]
        key = _derive_key(salt, _ITERATIONS)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
        return plaintext.decode()
    except Exception:
        pass
    # Legacy fallback: 12-byte nonce + ciphertext (static salt, 100k iterations)
    logger.warning(
        "Decrypting value with legacy format (static salt, 100k iterations). "
        "Re-encrypt this value to upgrade to the new format."
    )
    nonce = combined[:12]
    ciphertext = combined[12:]
    key = _derive_key(_LEGACY_SALT, _LEGACY_ITERATIONS)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    return plaintext.decode()
