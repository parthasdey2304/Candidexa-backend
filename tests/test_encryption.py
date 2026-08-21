"""Tests for encryption."""

from app.core.crypto import (
    encrypt_field,
    decrypt_field,
    blind_index,
    hash_sha256,
)


class TestEncryption:
    """Tests for field-level encryption."""

    def test_encrypt_decrypt_roundtrip(self):
        """encrypt_field and decrypt_field should round-trip."""
        test_values = [
            "simple string",
            "user@example.com",
            "555-123-4567",
            "Résumé with unicode: café",
            "Special chars: !@#$%^&*()",
            "",  # empty string
        ]
        for value in test_values:
            encrypted = encrypt_field(value)
            decrypted = decrypt_field(encrypted)
            assert decrypted == value, f"Failed for: {value}"

    def test_encrypt_none(self):
        """encrypt_field and decrypt_field should handle None."""
        assert encrypt_field(None) is None
        assert decrypt_field(None) is None

    def test_blind_index_deterministic(self):
        """blind_index should be deterministic for same input."""
        test_values = [
            "user@example.com",
            "555-123-4567",
            "test",
        ]
        for value in test_values:
            idx1 = blind_index(value)
            idx2 = blind_index(value)
            assert idx1 == idx2, f"Failed for: {value}"

    def test_blind_index_unique(self):
        """blind_index should produce different values for different inputs."""
        idx1 = blind_index("user1@example.com")
        idx2 = blind_index("user2@example.com")
        assert idx1 != idx2

    def test_hash_sha256_deterministic(self):
        """hash_sha256 should be deterministic."""
        assert hash_sha256("test") == hash_sha256("test")
        assert hash_sha256("test") != hash_sha256("other")