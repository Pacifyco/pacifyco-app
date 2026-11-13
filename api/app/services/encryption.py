"""Encrypting sensitive sitter fields at rest (CLAUDE.md section 7): health disclosure and bank
payout details are admin-only and encrypted, never shown to parents. One server-held symmetric key
(FIELD_ENCRYPTION_KEY), not a KMS or per-record keys -- nothing here names or needs key rotation yet.

The key is passed in by the caller (from the request's own Settings, via FastAPI's dependency
injection) rather than read from a global settings singleton, so tests can configure it per app
instance the same way app.services.storage threads its settings through."""

from cryptography.fernet import Fernet, InvalidToken


def _fernet(key: str) -> Fernet:
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set to read or write this field")
    return Fernet(key.encode())


def encrypt(key: str, plaintext: str) -> bytes:
    return _fernet(key).encrypt(plaintext.encode())


def decrypt(key: str, data: bytes) -> str:
    try:
        return _fernet(key).decrypt(data).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt this value") from exc
