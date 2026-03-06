"""Encryption utilities for sensitive data using Fernet (cryptography)."""

from cryptography.fernet import Fernet, InvalidToken


class EncryptionError(Exception):
    """Raised when encryption/decryption operations fail."""

    pass


class EncryptionManager:
    """Manages encryption and decryption of sensitive data using Fernet.

    Fernet provides authenticated encryption ensuring data cannot be read
    or modified without the key.
    """

    def __init__(self, key: str | bytes) -> None:
        """Initialize encryption manager with a Fernet key.

        Args:
            key: A URL-safe base64-encoded 32-byte Fernet key.
                 Can be generated with `EncryptionManager.generate_key()`.

        Raises:
            ValueError: If the key is invalid.
        """
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    @staticmethod
    def generate_key() -> str:
        """Generate a new Fernet encryption key.

        Returns:
            A URL-safe base64-encoded 32-byte key.
            Store this securely and use it to initialize EncryptionManager.
        """
        return Fernet.generate_key().decode()

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext data.

        Args:
            plaintext: The string to encrypt.

        Returns:
            URL-safe base64-encoded encrypted token.

        Raises:
            EncryptionError: If encryption fails.
        """
        try:
            token = self._fernet.encrypt(plaintext.encode())
            return token.decode()
        except Exception as e:
            raise EncryptionError(f"Failed to encrypt data: {e}") from e

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt encrypted data.

        Args:
            ciphertext: The encrypted token to decrypt.

        Returns:
            The decrypted plaintext string.

        Raises:
            EncryptionError: If decryption fails (invalid token or wrong key).
        """
        try:
            if isinstance(ciphertext, str):
                ciphertext = ciphertext.encode()
            plaintext = self._fernet.decrypt(ciphertext)
            return plaintext.decode()
        except InvalidToken as e:
            raise EncryptionError("Invalid or corrupted encryption token") from e
        except Exception as e:
            raise EncryptionError(f"Failed to decrypt data: {e}") from e


def create_encryption_manager(key: str | None = None) -> EncryptionManager:
    """Factory function to create an EncryptionManager from settings or explicit key.

    Args:
        key: Optional explicit encryption key. If not provided, uses
             VIEW_KEY_ENCRYPTION_KEY from settings.

    Returns:
        Configured EncryptionManager instance.

    Raises:
        ValueError: If no key is provided and settings key is empty.
    """
    import os

    if key is None:
        # Avoid requiring full Settings (which may need BOT_TOKEN) when only the encryption key is needed.
        key = os.getenv("VIEW_KEY_ENCRYPTION_KEY", "")

    if not key:
        raise ValueError(
            "Encryption key is required. Set VIEW_KEY_ENCRYPTION_KEY "
            "environment variable or pass key explicitly."
        )

    return EncryptionManager(key)
