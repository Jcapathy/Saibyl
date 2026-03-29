import os

from app.services.markets.encryption import decrypt_key, encrypt_key


def test_encrypt_decrypt_roundtrip():
    os.environ["MARKET_KEY_ENCRYPTION_SECRET"] = "test-secret-key-32chars-minimum!"
    original = "sk_kalshi_my_secret_api_key_12345"
    encrypted = encrypt_key(original)
    decrypted = decrypt_key(encrypted)
    assert decrypted == original


def test_encrypted_differs_from_plaintext():
    os.environ["MARKET_KEY_ENCRYPTION_SECRET"] = "test-secret-key-32chars-minimum!"
    original = "my-api-key"
    encrypted = encrypt_key(original)
    assert encrypted != original


def test_different_encryptions_differ():
    os.environ["MARKET_KEY_ENCRYPTION_SECRET"] = "test-secret-key-32chars-minimum!"
    original = "same-key"
    enc1 = encrypt_key(original)
    enc2 = encrypt_key(original)
    # AES-GCM uses random nonce, so two encryptions of same plaintext differ
    assert enc1 != enc2
    # But both decrypt to the same value
    assert decrypt_key(enc1) == original
    assert decrypt_key(enc2) == original


def test_wrong_key_fails():
    os.environ["MARKET_KEY_ENCRYPTION_SECRET"] = "key-one-32-chars-padded-properly!"
    encrypted = encrypt_key("my-secret")
    os.environ["MARKET_KEY_ENCRYPTION_SECRET"] = "key-two-different-32chars-here!!"
    import pytest
    with pytest.raises(Exception):
        decrypt_key(encrypted)
