"""Application-level encryption for Google OAuth tokens at rest (stage 2, §8).

Standard authenticated encryption (``cryptography`` Fernet, AES-128-CBC +
HMAC-SHA256), never custom XOR/base64. The key comes from the environment
(``GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY``): it lives outside the
database and outside source control, so a leaked database dump does not
leak usable Google credentials.

Ciphertext is prefixed with ``enc.v1:`` so stored values can never be
silently confused with plaintext, and decryption of an unmarked value is a
loud error instead of a quiet data-integrity lie.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

# Environment variable holding the base64-encoded Fernet key
# (cryptography.fernet.Fernet.generate_key()).
KEY_ENV_VAR = "GC_DASHBOARD_OAUTH_TOKEN_ENCRYPTION_KEY"

_CIPHERTEXT_PREFIX = "enc.v1:"


class TokenEncryptionError(RuntimeError):
    """Raised when the key is missing/invalid or a value cannot be decrypted."""


def _fernet() -> Fernet:
    raw = os.environ.get(KEY_ENV_VAR, "")
    if not raw:
        raise TokenEncryptionError(
            f"{KEY_ENV_VAR} is not set: Google OAuth tokens cannot be "
            "encrypted at rest. Generate a key with "
            '`python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"`.'
        )
    try:
        return Fernet(raw.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise TokenEncryptionError(
            f"{KEY_ENV_VAR} is not a valid Fernet key: {exc!r}"
        ) from exc


def generate_key() -> str:
    """A fresh Fernet key for operators (used by tools/generate_hosted_secrets.py)."""
    return Fernet.generate_key().decode("ascii")


def encrypt(plaintext: str) -> str:
    """Encrypt a token field; returns a ``enc.v1:``-prefixed ciphertext."""
    return _CIPHERTEXT_PREFIX + _fernet().encrypt(plaintext.encode("utf-8")).decode(
        "ascii"
    )


def decrypt(value: str) -> str:
    """Decrypt a ``enc.v1:``-prefixed value.

    A value without the prefix is rejected instead of returned as-is: the
    database must never contain plaintext credentials, and silently
    accepting one would hide a broken write path.
    """
    if not value.startswith(_CIPHERTEXT_PREFIX):
        raise TokenEncryptionError(
            "Stored OAuth credential is not encrypted "
            "(missing 'enc.v1:' prefix) — refusing to use it."
        )
    try:
        return (
            _fernet()
            .decrypt(value[len(_CIPHERTEXT_PREFIX) :].encode("ascii"))
            .decode("utf-8")
        )
    except InvalidToken as exc:
        # Wrong key, truncated value or tampered ciphertext: same treatment.
        raise TokenEncryptionError(
            "Stored OAuth credential cannot be decrypted."
        ) from exc


def key_is_configured() -> bool:
    return bool(os.environ.get(KEY_ENV_VAR, ""))
