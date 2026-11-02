"""Encrypting sensitive sitter fields at rest (CLAUDE.md section 7): health disclosure and bank
payout details are admin-only and encrypted, never shown to parents. One server-held symmetric key
(FIELD_ENCRYPTION_KEY), not a KMS or per-record keys -- nothing here names or needs key rotation yet."""

from cryptography.fernet import Fernet, InvalidToken

from app.settings import get_settings


def _fernet() -> Fernet:
    key = get_settings().field_encryption_key
    if not key:
        raise RuntimeError("FIELD_ENCRYPTION_KEY must be set to read or write this field")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(data: bytes) -> str:
    try:
        return _fernet().decrypt(data).decode()
    except InvalidToken as exc:
        raise ValueError("Could not decrypt this value") from exc
