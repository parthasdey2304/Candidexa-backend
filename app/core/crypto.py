from __future__ import annotations
import base64
import hashlib
import hmac
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from app.core.config import settings

# Nonce must NEVER repeat under the same key. AES-GCM nonce is 96 bits = 12 bytes.
# We use random 12-byte nonces - collision probability for 2^32 messages is ~2^-32.
# For high-volume fields, switch to deterministic nonce = HMAC(key, plaintext)[:12].

def _field_key() -> bytes:
    return base64.b64decode(settings.FIELD_ENCRYPTION_KEY)

def _blind_key() -> bytes:
    return base64.b64decode(settings.FIELD_BLIND_INDEX_KEY)


def encrypt_field(plaintext: str | None) -> str | None:
    """AES-256-GCM. Returns base64(nonce || ciphertext || tag)."""
    if plaintext is None:
        return None
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)
    key = _field_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(token: str | None) -> str | None:
    if token is None:
        return None
    key = _field_key()
    raw = base64.b64decode(token)
    nonce, ct = raw[:12], raw[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, associated_data=None).decode("utf-8")


def blind_index(value: str | None) -> str | None:
    """HMAC-SHA256 keyed hash. Used as a searchable index for encrypted fields.

    Store this alongside the ciphertext so you can do WHERE email_hmac = ? without
    decrypting every row. HMAC prevents rainbow-table / dictionary attacks.
    """
    if value is None:
        return None
    return hmac.new(_blind_key(), value.encode("utf-8"), hashlib.sha256).hexdigest()


def hash_sha256(value: str) -> str:
    """Plain SHA-256 for non-secret integrity (cache keys, request IDs, etc.)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()