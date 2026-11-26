"""Cryptographic utilities for protecting bot tokens and sensitive configuration.

Uses AES-128-CBC with HMAC-SHA256 (Fernet) authenticated symmetric encryption.
"""

from __future__ import annotations

import argparse

from cryptography.fernet import Fernet, InvalidToken


def generate_encryption_key() -> str:
    """Generate a new cryptographically secure 32-byte URL-safe base64 key."""
    return Fernet.generate_key().decode("utf-8")


def encrypt_token(plain_token: str, key: str | bytes) -> str:
    """Encrypt a plaintext bot token with the given Fernet key."""
    if isinstance(key, str):
        key = key.encode("utf-8")
    cipher = Fernet(key)
    return cipher.encrypt(plain_token.strip().encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted_token: str, key: str | bytes) -> str:
    """Decrypt an encrypted bot token with the given Fernet key.

    Raises:
        ValueError: If the key or ciphertext is invalid or tampered with.
    """
    if isinstance(key, str):
        key = key.encode("utf-8")
    try:
        cipher = Fernet(key)
        return cipher.decrypt(encrypted_token.strip().encode("utf-8")).decode("utf-8")
    except (InvalidToken, Exception) as exc:
        raise ValueError(
            "Failed to decrypt bot token. Ensure BOT_TOKEN_ENCRYPTION_KEY matches the key used during encryption."
        ) from exc


def main() -> None:
    """CLI tool for generating keys and encrypting tokens."""
    parser = argparse.ArgumentParser(description="Encrypt sensitive secrets for telegram-orders-bot")
    parser.add_argument("token", nargs="?", help="Plaintext token to encrypt")
    parser.add_argument("--key", help="Existing encryption key (if omitted, a new one is generated)")
    args = parser.parse_args()

    token = args.token
    if not token:
        token = input("Enter the bot token to encrypt: ").strip()

    key = args.key or generate_encryption_key()
    encrypted = encrypt_token(token, key)

    print("\n" + "=" * 60)
    print("🔒 SECRET ENCRYPTION COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("\nAdd the following lines to your .env file or environment:\n")
    print(f"BOT_TOKEN_ENCRYPTION_KEY={key}")
    print(f"TELEGRAM_BOT_TOKEN_ENCRYPTED={encrypted}")
    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    main()
