"""Unit tests for Redis schema module."""

from datetime import datetime, timedelta, timezone

import pytest

import pytest

from xmr_cheque_bot.encryption import EncryptionManager
from xmr_cheque_bot.redis_schema import (
    TTLConfig,
    ChequeRecord,
    ChequeStatus,
    RedisKeys,
    UserRecord,
    UserWallet,
    get_cheque_ttl,
)


@pytest.fixture(autouse=True)
def _set_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure Settings can instantiate during unit tests."""
    monkeypatch.setenv("BOT_TOKEN", "test")
    monkeypatch.setenv("VIEW_KEY_ENCRYPTION_KEY", EncryptionManager.generate_key())


class TestRedisKeys:
    """Tests for Redis key pattern generators."""
    
    def test_user_key(self) -> None:
        """Test user key generation."""
        assert RedisKeys.user("12345") == "user:12345"
        assert RedisKeys.user(12345) == "user:12345"
    
    def test_user_wallet_key(self) -> None:
        """Test user wallet key generation."""
        assert RedisKeys.user_wallet("12345") == "user:12345:wallet"
        assert RedisKeys.user_wallet(12345) == "user:12345:wallet"
    
    def test_user_cheques_index_key(self) -> None:
        """Test user cheques index key generation."""
        assert RedisKeys.user_cheques_index("12345") == "user_cheques:12345"
    
    def test_cheque_key(self) -> None:
        """Test cheque key generation."""
        assert RedisKeys.cheque("abc-123") == "cheque:abc-123"
    
    def test_rate_limit_cheque_key(self) -> None:
        """Test cheque rate limit key generation."""
        assert RedisKeys.rate_limit_cheque("12345") == "ratelimit:cheque:12345"
    
    def test_rate_limit_wallet_bind_key(self) -> None:
        """Test wallet bind rate limit key generation."""
        assert RedisKeys.rate_limit_wallet_bind("12345") == "ratelimit:wallet_bind:12345"
    
    def test_keys_are_unique(self) -> None:
        """Test that different types generate different keys."""
        user_id = "12345"
        cheque_id = "cheque-abc"
        
        keys = [
            RedisKeys.user(user_id),
            RedisKeys.user_wallet(user_id),
            RedisKeys.user_cheques_index(user_id),
            RedisKeys.cheque(cheque_id),
            RedisKeys.rate_limit_cheque(user_id),
            RedisKeys.rate_limit_wallet_bind(user_id),
        ]
        
        # All keys should be unique
        assert len(set(keys)) == len(keys)


class TestChequeStatus:
    """Tests for ChequeStatus enum."""
    
    def test_status_values(self) -> None:
        """Test status enum values."""
        assert ChequeStatus.PENDING == "pending"
        assert ChequeStatus.MEMPOOL == "mempool"
        assert ChequeStatus.CONFIRMING == "confirming"
        assert ChequeStatus.CONFIRMED == "confirmed"
        assert ChequeStatus.EXPIRED == "expired"
        assert ChequeStatus.CANCELLED == "cancelled"
    
    def test_status_comparison(self) -> None:
        """Test status can be compared with strings."""
        assert ChequeStatus.PENDING == "pending"
        assert ChequeStatus.CONFIRMED == "confirmed"


class TestTTLConfig:
    """Tests for TTL configuration."""
    
    def test_default_values(self) -> None:
        """Test default TTL values."""
        config = TTLConfig()
        
        assert config.CHEQUE_PENDING_SECONDS == 3600
        assert config.RATE_LIMIT_CHEQUE_SECONDS == 600
        assert config.RATE_LIMIT_WALLET_BIND_SECONDS == 600
        assert config.COMPLETED_CHEQUE_RETENTION_DAYS == 7
    
    def test_custom_values(self) -> None:
        """Test custom TTL configuration."""
        config = TTLConfig(
            CHEQUE_PENDING_SECONDS=7200,
            RATE_LIMIT_CHEQUE_SECONDS=300,
        )
        
        assert config.CHEQUE_PENDING_SECONDS == 7200
        assert config.RATE_LIMIT_CHEQUE_SECONDS == 300
        assert config.RATE_LIMIT_WALLET_BIND_SECONDS == 600  # unchanged


class TestGetChequeTTL:
    """Tests for get_cheque_ttl function."""
    
    def test_pending_ttl(self) -> None:
        """Test TTL for pending status."""
        config = TTLConfig(CHEQUE_PENDING_SECONDS=3600)
        
        ttl = get_cheque_ttl(ChequeStatus.PENDING, config)
        assert ttl == 3600
    
    def test_mempool_ttl(self) -> None:
        """Test TTL for mempool status (extended)."""
        config = TTLConfig(CHEQUE_PENDING_SECONDS=3600)
        
        ttl = get_cheque_ttl(ChequeStatus.MEMPOOL, config)
        assert ttl == 3600 + 3600  # pending + 1 hour extension
    
    def test_confirming_ttl(self) -> None:
        """Test TTL for confirming status (extended)."""
        config = TTLConfig(CHEQUE_PENDING_SECONDS=3600)
        
        ttl = get_cheque_ttl(ChequeStatus.CONFIRMING, config)
        assert ttl == 3600 + 3600
    
    def test_confirmed_ttl(self) -> None:
        """Test TTL for confirmed status (retention)."""
        config = TTLConfig(COMPLETED_CHEQUE_RETENTION_DAYS=7)
        
        ttl = get_cheque_ttl(ChequeStatus.CONFIRMED, config)
        assert ttl == 7 * 86400
    
    def test_expired_ttl(self) -> None:
        """Test TTL for expired status (retention)."""
        config = TTLConfig(COMPLETED_CHEQUE_RETENTION_DAYS=7)
        
        ttl = get_cheque_ttl(ChequeStatus.EXPIRED, config)
        assert ttl == 7 * 86400
    
    def test_cancelled_ttl(self) -> None:
        """Test TTL for cancelled status (retention)."""
        config = TTLConfig(COMPLETED_CHEQUE_RETENTION_DAYS=3)
        
        ttl = get_cheque_ttl(ChequeStatus.CANCELLED, config)
        assert ttl == 3 * 86400
    
    def test_default_config(self) -> None:
        """Test function works with default config."""
        ttl = get_cheque_ttl(ChequeStatus.PENDING)
        assert ttl == TTLConfig().CHEQUE_PENDING_SECONDS


class TestUserWallet:
    """Tests for UserWallet dataclass."""
    
    def test_create_wallet(self) -> None:
        """Test creating a UserWallet."""
        wallet = UserWallet(
            user_id="12345",
            monero_address="44...test",
            encrypted_view_key="encrypted:abc123",
            encrypted_wallet_password="encrypted:pw",
            wallet_file_name="wallet_12345",
        )
        
        assert wallet.user_id == "12345"
        assert wallet.monero_address == "44...test"
        assert wallet.encrypted_view_key == "encrypted:abc123"
        assert wallet.wallet_file_name == "wallet_12345"
    
    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(timezone.utc)
        wallet = UserWallet(
            user_id="12345",
            monero_address="44...test",
            encrypted_view_key="encrypted:abc123",
            encrypted_wallet_password="encrypted:pw",
            created_at=now,
            updated_at=now,
        )
        
        data = wallet.to_dict()
        
        assert data["user_id"] == "12345"
        assert data["monero_address"] == "44...test"
        assert data["encrypted_view_key"] == "encrypted:abc123"
        assert data["created_at"] == now.isoformat()
        assert data["updated_at"] == now.isoformat()
    
    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "user_id": "12345",
            "monero_address": "44...test",
            "encrypted_view_key": "encrypted:abc123",
            "wallet_file_name": "wallet_12345",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        
        wallet = UserWallet.from_dict(data)
        
        assert wallet.user_id == "12345"
        assert wallet.monero_address == "44...test"
        assert wallet.encrypted_view_key == "encrypted:abc123"
        assert wallet.wallet_file_name == "wallet_12345"
        assert wallet.created_at == now
    
    def test_from_dict_optional_fields(self) -> None:
        """Test from_dict handles optional wallet_file_name."""
        now = datetime.now(timezone.utc)
        data = {
            "user_id": "12345",
            "monero_address": "44...test",
            "encrypted_view_key": "encrypted:abc123",
            "wallet_file_name": "",  # empty string
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        
        wallet = UserWallet.from_dict(data)
        
        assert wallet.wallet_file_name is None
    
    def test_roundtrip(self) -> None:
        """Test to_dict -> from_dict roundtrip preserves data."""
        wallet = UserWallet(
            user_id="12345",
            monero_address="44...test",
            encrypted_view_key="encrypted:abc123",
            encrypted_wallet_password="encrypted:pw",
            wallet_file_name="wallet_12345",
        )
        
        data = wallet.to_dict()
        restored = UserWallet.from_dict(data)
        
        assert restored.user_id == wallet.user_id
        assert restored.monero_address == wallet.monero_address
        assert restored.encrypted_view_key == wallet.encrypted_view_key
        assert restored.wallet_file_name == wallet.wallet_file_name


class TestChequeRecord:
    """Tests for ChequeRecord dataclass."""
    
    def test_create_cheque(self) -> None:
        """Test creating a ChequeRecord."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        
        cheque = ChequeRecord(
            cheque_id="cheque-abc",
            user_id="12345",
            amount_rub=1000,
            amount_atomic_expected=5000000000001,
            monero_address="44...test",
            min_height=3000000,
            status=ChequeStatus.PENDING,
            created_at=now,
            expires_at=expires,
            amount_xmr_display="0.005000000001 XMR",
        )
        
        assert cheque.cheque_id == "cheque-abc"
        assert cheque.user_id == "12345"
        assert cheque.amount_rub == 1000
        assert cheque.amount_atomic_expected == 5000000000001
        assert cheque.status == ChequeStatus.PENDING
    
    def test_auto_expires_at(self, monkeypatch) -> None:
        """Test expires_at is auto-set from settings."""
        monkeypatch.setenv("CHEQUE_TTL_SECONDS", "7200")

        now = datetime.now(timezone.utc)

        # Reset cached settings to pick up env var
        import xmr_cheque_bot.config as config_module
        config_module._settings = None

        cheque = ChequeRecord(
            cheque_id="test",
            user_id="123",
            amount_rub=100,
            amount_atomic_expected=1000,
            monero_address="44",
            min_height=1,
        )
        
        assert cheque.expires_at is not None
        assert cheque.expires_at > now
    
    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        
        cheque = ChequeRecord(
            cheque_id="cheque-abc",
            user_id="12345",
            amount_rub=1000,
            amount_atomic_expected=5000000000001,
            monero_address="44...test",
            min_height=3000000,
            status=ChequeStatus.PENDING,
            created_at=now,
            expires_at=expires,
            amount_xmr_display="0.005000000001 XMR",
            description="Test cheque",
        )
        
        data = cheque.to_dict()
        
        assert data["cheque_id"] == "cheque-abc"
        assert data["user_id"] == "12345"
        assert data["amount_rub"] == "1000"
        assert data["amount_atomic_expected"] == "5000000000001"
        assert data["monero_address"] == "44...test"
        assert data["min_height"] == "3000000"
        assert data["status"] == "pending"
        assert data["amount_xmr_display"] == "0.005000000001 XMR"
        assert data["description"] == "Test cheque"
        assert data["created_at"] == now.isoformat()
        assert data["expires_at"] == expires.isoformat()
    
    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        paid = now + timedelta(minutes=30)
        
        data = {
            "cheque_id": "cheque-abc",
            "user_id": "12345",
            "amount_rub": "1000",
            "amount_atomic_expected": "5000000000001",
            "monero_address": "44...test",
            "min_height": "3000000",
            "status": "mempool",
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "paid_at": paid.isoformat(),
            "tx_hash": "abc123...",
            "tx_height": "3000005",
            "confirmations": "0",
            "amount_xmr_display": "0.005000000001 XMR",
            "description": "Test",
        }
        
        cheque = ChequeRecord.from_dict(data)
        
        assert cheque.cheque_id == "cheque-abc"
        assert cheque.amount_rub == 1000
        assert cheque.amount_atomic_expected == 5000000000001
        assert cheque.status == ChequeStatus.MEMPOOL
        assert cheque.tx_hash == "abc123..."
        assert cheque.tx_height == 3000005
        assert cheque.confirmations == 0
    
    def test_from_dict_missing_optional(self) -> None:
        """Test from_dict handles missing/empty optional fields."""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)
        
        data = {
            "cheque_id": "cheque-abc",
            "user_id": "12345",
            "amount_rub": "1000",
            "amount_atomic_expected": "5000000000001",
            "monero_address": "44...test",
            "min_height": "3000000",
            "created_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "paid_at": "",
            "tx_hash": "",
            "tx_height": "",
            "confirmations": "",
        }
        
        cheque = ChequeRecord.from_dict(data)
        
        assert cheque.expires_at == expires
        assert cheque.paid_at is None
        assert cheque.tx_hash is None
        assert cheque.tx_height is None
        assert cheque.confirmations == 0
    
    def test_is_expired(self) -> None:
        """Test is_expired check."""
        now = datetime.now(timezone.utc)
        
        # Not expired
        cheque = ChequeRecord(
            cheque_id="test",
            user_id="123",
            amount_rub=100,
            amount_atomic_expected=1000,
            monero_address="44",
            min_height=1,
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        assert not cheque.is_expired()
        
        # Expired
        expired = ChequeRecord(
            cheque_id="test2",
            user_id="123",
            amount_rub=100,
            amount_atomic_expected=1000,
            monero_address="44",
            min_height=1,
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
        assert expired.is_expired()
    
    def test_is_final(self) -> None:
        """Test is_final check for terminal statuses."""
        base_kwargs = {
            "cheque_id": "test",
            "user_id": "123",
            "amount_rub": 100,
            "amount_atomic_expected": 1000,
            "monero_address": "44",
            "min_height": 1,
        }
        
        # Non-final statuses
        assert not ChequeRecord(status=ChequeStatus.PENDING, **base_kwargs).is_final()
        assert not ChequeRecord(status=ChequeStatus.MEMPOOL, **base_kwargs).is_final()
        assert not ChequeRecord(status=ChequeStatus.CONFIRMING, **base_kwargs).is_final()
        
        # Final statuses
        assert ChequeRecord(status=ChequeStatus.CONFIRMED, **base_kwargs).is_final()
        assert ChequeRecord(status=ChequeStatus.EXPIRED, **base_kwargs).is_final()
        assert ChequeRecord(status=ChequeStatus.CANCELLED, **base_kwargs).is_final()
    
    def test_roundtrip(self) -> None:
        """Test to_dict -> from_dict roundtrip preserves data."""
        now = datetime.now(timezone.utc)
        
        cheque = ChequeRecord(
            cheque_id="cheque-abc",
            user_id="12345",
            amount_rub=1000,
            amount_atomic_expected=5000000000001,
            monero_address="44...test",
            min_height=3000000,
            status=ChequeStatus.CONFIRMING,
            created_at=now,
            expires_at=now + timedelta(hours=1),
            tx_hash="abc123",
            tx_height=3000005,
            confirmations=3,
            amount_xmr_display="0.005 XMR",
            description="Test",
        )
        
        data = cheque.to_dict()
        restored = ChequeRecord.from_dict(data)
        
        assert restored.cheque_id == cheque.cheque_id
        assert restored.user_id == cheque.user_id
        assert restored.amount_rub == cheque.amount_rub
        assert restored.amount_atomic_expected == cheque.amount_atomic_expected
        assert restored.status == cheque.status
        assert restored.tx_hash == cheque.tx_hash
        assert restored.confirmations == cheque.confirmations


class TestUserRecord:
    """Tests for UserRecord dataclass."""
    
    def test_create_user(self) -> None:
        """Test creating a UserRecord."""
        user = UserRecord(user_id="12345")
        
        assert user.user_id == "12345"
        assert user.language == "en"
    
    def test_create_user_russian(self) -> None:
        """Test creating a UserRecord with Russian language."""
        user = UserRecord(user_id="12345", language="ru")
        
        assert user.language == "ru"
    
    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        now = datetime.now(timezone.utc)
        user = UserRecord(
            user_id="12345",
            language="ru",
            created_at=now,
            last_activity_at=now,
        )
        
        data = user.to_dict()
        
        assert data["user_id"] == "12345"
        assert data["language"] == "ru"
        assert data["created_at"] == now.isoformat()
        assert data["last_activity_at"] == now.isoformat()
    
    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "user_id": "12345",
            "language": "en",
            "created_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
        }
        
        user = UserRecord.from_dict(data)
        
        assert user.user_id == "12345"
        assert user.language == "en"
        assert user.created_at == now
    
    def test_from_dict_default_language(self) -> None:
        """Test from_dict uses default language if not specified."""
        now = datetime.now(timezone.utc)
        data = {
            "user_id": "12345",
            "created_at": now.isoformat(),
            "last_activity_at": now.isoformat(),
        }
        
        user = UserRecord.from_dict(data)
        
        assert user.language == "en"
    
    def test_roundtrip(self) -> None:
        """Test to_dict -> from_dict roundtrip preserves data."""
        user = UserRecord(user_id="12345", language="ru")
        
        data = user.to_dict()
        restored = UserRecord.from_dict(data)
        
        assert restored.user_id == user.user_id
        assert restored.language == user.language
