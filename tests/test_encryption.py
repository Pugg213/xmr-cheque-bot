"""Unit tests for encryption module."""

import pytest

from xmr_cheque_bot.encryption import EncryptionError, EncryptionManager, create_encryption_manager


class TestEncryptionManager:
    """Tests for EncryptionManager class."""

    def test_generate_key(self) -> None:
        """Test key generation produces valid Fernet key."""
        key = EncryptionManager.generate_key()

        # Key should be a string
        assert isinstance(key, str)
        # Fernet keys are URL-safe base64, 32 bytes encoded = ~44 chars
        assert len(key) == 44
        # Key should contain only URL-safe base64 characters
        assert all(
            c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_=" for c in key
        )

    def test_encrypt_decrypt_roundtrip(self) -> None:
        """Test encrypting and decrypting returns original data."""
        key = EncryptionManager.generate_key()
        manager = EncryptionManager(key)

        plaintext = "my secret view key: abc123..."
        ciphertext = manager.encrypt(plaintext)
        decrypted = manager.decrypt(ciphertext)

        assert decrypted == plaintext

    def test_encrypt_produces_different_output(self) -> None:
        """Test that encryption produces different ciphertext for same plaintext."""
        key = EncryptionManager.generate_key()
        manager = EncryptionManager(key)

        plaintext = "test data"
        ciphertext1 = manager.encrypt(plaintext)
        ciphertext2 = manager.encrypt(plaintext)

        # Same plaintext should produce different ciphertexts (Fernet uses IV)
        assert ciphertext1 != ciphertext2
        # But both should decrypt to same plaintext
        assert manager.decrypt(ciphertext1) == plaintext
        assert manager.decrypt(ciphertext2) == plaintext

    def test_decrypt_with_wrong_key(self) -> None:
        """Test decryption with wrong key raises EncryptionError."""
        key1 = EncryptionManager.generate_key()
        key2 = EncryptionManager.generate_key()

        manager1 = EncryptionManager(key1)
        manager2 = EncryptionManager(key2)

        plaintext = "secret"
        ciphertext = manager1.encrypt(plaintext)

        with pytest.raises(EncryptionError, match="Invalid or corrupted"):
            manager2.decrypt(ciphertext)

    def test_decrypt_invalid_token(self) -> None:
        """Test decrypting invalid token raises EncryptionError."""
        key = EncryptionManager.generate_key()
        manager = EncryptionManager(key)

        with pytest.raises(EncryptionError, match="Invalid or corrupted"):
            manager.decrypt("not-a-valid-token")

    def test_encrypt_empty_string(self) -> None:
        """Test encrypting empty string works."""
        key = EncryptionManager.generate_key()
        manager = EncryptionManager(key)

        ciphertext = manager.encrypt("")
        decrypted = manager.decrypt(ciphertext)

        assert decrypted == ""

    def test_encrypt_unicode(self) -> None:
        """Test encrypting unicode characters works."""
        key = EncryptionManager.generate_key()
        manager = EncryptionManager(key)

        plaintext = "Привет мир 🌍 ñ café"
        ciphertext = manager.encrypt(plaintext)
        decrypted = manager.decrypt(ciphertext)

        assert decrypted == plaintext

    def test_init_with_bytes_key(self) -> None:
        """Test EncryptionManager accepts bytes key."""
        key_str = EncryptionManager.generate_key()
        key_bytes = key_str.encode()

        manager = EncryptionManager(key_bytes)

        plaintext = "test"
        ciphertext = manager.encrypt(plaintext)
        decrypted = manager.decrypt(ciphertext)

        assert decrypted == plaintext

    def test_decrypt_bytes_input(self) -> None:
        """Test decrypt accepts bytes input."""
        key = EncryptionManager.generate_key()
        manager = EncryptionManager(key)

        plaintext = "test"
        ciphertext_str = manager.encrypt(plaintext)
        ciphertext_bytes = ciphertext_str.encode()

        decrypted = manager.decrypt(ciphertext_bytes)
        assert decrypted == plaintext


class TestCreateEncryptionManager:
    """Tests for create_encryption_manager factory function."""

    def test_create_with_explicit_key(self) -> None:
        """Test factory with explicit key."""
        key = EncryptionManager.generate_key()
        manager = create_encryption_manager(key=key)

        assert isinstance(manager, EncryptionManager)

        # Verify it works
        ciphertext = manager.encrypt("test")
        assert manager.decrypt(ciphertext) == "test"

    def test_create_without_key_raises(self, monkeypatch) -> None:
        """Test factory raises without key when settings empty."""
        monkeypatch.setenv("VIEW_KEY_ENCRYPTION_KEY", "")

        with pytest.raises(ValueError, match="Encryption key is required"):
            create_encryption_manager()

    def test_create_from_environment(self, monkeypatch) -> None:
        """Test factory creates manager from environment variable."""
        key = EncryptionManager.generate_key()
        monkeypatch.setenv("VIEW_KEY_ENCRYPTION_KEY", key)

        manager = create_encryption_manager()
        assert isinstance(manager, EncryptionManager)

        # Verify it works
        ciphertext = manager.encrypt("test")
        assert manager.decrypt(ciphertext) == "test"
