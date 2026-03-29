import hashlib


def test_key_generation_format():
    from app.api.api_keys import _generate_api_key

    full_key, key_hash, key_prefix = _generate_api_key("live")
    assert full_key.startswith("sk_live_")
    assert len(full_key) > 20
    assert key_prefix == full_key[:12]
    assert key_hash == hashlib.sha256(full_key.encode()).hexdigest()


def test_key_generation_test_env():
    from app.api.api_keys import _generate_api_key

    full_key, _, _ = _generate_api_key("test")
    assert full_key.startswith("sk_test_")


def test_keys_are_unique():
    from app.api.api_keys import _generate_api_key

    keys = set()
    for _ in range(50):
        full_key, _, _ = _generate_api_key("live")
        assert full_key not in keys
        keys.add(full_key)


def test_hash_is_deterministic():
    from app.api.api_keys import _generate_api_key

    full_key, key_hash, _ = _generate_api_key("live")
    recomputed = hashlib.sha256(full_key.encode()).hexdigest()
    assert key_hash == recomputed
