from __future__ import annotations
from sqlalchemy import String, TypeDecorator
from app.core.crypto import encrypt_field, decrypt_field


class EncryptedString(TypeDecorator):
    """Transparent AES-256-GCM column. Use for PII you only need to decrypt."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_field(value)

    def process_result_value(self, value, dialect):
        return decrypt_field(value)


class EncryptedLargeString(TypeDecorator):
    """For resume text / long PII. Stored as TEXT in DB."""
    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_field(value)

    def process_result_value(self, value, dialect):
        return decrypt_field(value)