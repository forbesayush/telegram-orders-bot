import pytest

from bot.config import Config
from bot.security import decrypt_token, encrypt_token, generate_encryption_key


def test_encryption_roundtrip():
    key = generate_encryption_key()
    original_token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"

    encrypted = encrypt_token(original_token, key)
    assert encrypted != original_token
    assert len(encrypted) > 20

    decrypted = decrypt_token(encrypted, key)
    assert decrypted == original_token


def test_decrypt_invalid_key_raises_error():
    key1 = generate_encryption_key()
    key2 = generate_encryption_key()
    original_token = "123456789:ABCdefGHIjklMNOpqrSTUvwxYZ"

    encrypted = encrypt_token(original_token, key1)
    with pytest.raises(ValueError, match="Failed to decrypt"):
        decrypt_token(encrypted, key2)


def test_config_loads_encrypted_token(monkeypatch):
    key = generate_encryption_key()
    secret_token = "999888777:SecretEncryptedTokenValue"
    encrypted = encrypt_token(secret_token, key)

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setenv("BOT_TOKEN_ENCRYPTION_KEY", key)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_ENCRYPTED", encrypted)

    cfg = Config.from_env()
    assert cfg.bot_token == secret_token
