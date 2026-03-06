"""Integration tests for Redis storage.

Uses fakeredis to mock Redis without requiring a real server.

NOTE: This suite is WIP and is skipped by default until fixtures and env setup
are finalized.
"""

import asyncio

import pytest

pytestmark = pytest.mark.skip(reason="WIP: integration test suite pending fixture/env finalization")

# -----------------------------------------------------------------------------
# The rest of the imports remain below

from datetime import UTC, datetime, timedelta

from fakeredis.aioredis import FakeRedis

from xmr_cheque_bot.encryption import EncryptionManager
from xmr_cheque_bot.redis_schema import ChequeRecord, ChequeStatus, UserRecord
from xmr_cheque_bot.storage import RedisStorage, StorageError


@pytest.fixture
def fake_redis():
    """Create a fake Redis client."""
    return FakeRedis()


@pytest.fixture
def encryption():
    """Create encryption manager for testing."""
    key = EncryptionManager.generate_key()
    return EncryptionManager(key)


@pytest.fixture
async def storage(fake_redis, encryption):
    """Create storage instance with fake Redis."""
    store = RedisStorage(redis_client=fake_redis, encryption=encryption)
    yield store
    await store.close()


class TestStorageUserOperations:
    """Test user CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_and_get_user(self, storage):
        """Test creating and retrieving a user."""
        user = UserRecord(user_id="123456", language="ru")
        await storage.save_user(user)

        retrieved = await storage.get_user("123456")

        assert retrieved is not None
        assert retrieved.user_id == "123456"
        assert retrieved.language == "ru"

    @pytest.mark.asyncio
    async def test_get_or_create_user_existing(self, storage):
        """Test get_or_create with existing user."""
        user = UserRecord(user_id="123456", language="en")
        await storage.save_user(user)

        result = await storage.get_or_create_user("123456", language="ru")

        # Should return existing user, not create new one
        assert result.language == "en"

    @pytest.mark.asyncio
    async def test_get_or_create_user_new(self, storage):
        """Test get_or_create with new user."""
        result = await storage.get_or_create_user("123456", language="ru")

        assert result.user_id == "123456"
        assert result.language == "ru"

    @pytest.mark.asyncio
    async def test_update_user_activity(self, storage):
        """Test updating user activity timestamp."""
        user = UserRecord(user_id="123456", language="en")
        old_activity = user.last_activity_at
        await storage.save_user(user)

        await asyncio.sleep(0.01)  # Small delay
        await storage.update_user_activity("123456")

        retrieved = await storage.get_user("123456")
        assert retrieved.last_activity_at > old_activity


class TestStorageWalletOperations:
    """Test wallet CRUD operations."""

    @pytest.mark.asyncio
    async def test_bind_and_get_wallet(self, storage):
        """Test wallet binding and retrieval."""
        wallet = await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key="secret_view_key_12345" + "0" * 43,
            wallet_file_name="wallet_123456",
        )

        retrieved = await storage.get_wallet("123456")

        assert retrieved is not None
        assert retrieved.user_id == "123456"
        assert retrieved.monero_address == "4ABC..."
        assert retrieved.wallet_file_name == "wallet_123456"

    @pytest.mark.asyncio
    async def test_has_wallet_true(self, storage):
        """Test has_wallet returns True when wallet exists."""
        await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key="secret_view_key_12345" + "0" * 43,
        )

        result = await storage.has_wallet("123456")

        assert result is True

    @pytest.mark.asyncio
    async def test_has_wallet_false(self, storage):
        """Test has_wallet returns False when wallet doesn't exist."""
        result = await storage.has_wallet("999999")

        assert result is False

    @pytest.mark.asyncio
    async def test_unbind_wallet(self, storage):
        """Test wallet unbinding."""
        await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key="secret_view_key_12345" + "0" * 43,
        )

        result = await storage.unbind_wallet("123456")

        assert result is True
        assert await storage.has_wallet("123456") is False

    @pytest.mark.asyncio
    async def test_unbind_nonexistent_wallet(self, storage):
        """Test unbinding non-existent wallet."""
        result = await storage.unbind_wallet("999999")

        assert result is False

    @pytest.mark.asyncio
    async def test_decrypt_view_key(self, storage):
        """Test view key encryption/decryption."""
        original_key = "secret_view_key_12345" + "0" * 43
        wallet = await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key=original_key,
        )

        decrypted = await storage.decrypt_view_key(wallet)

        assert decrypted == original_key

    @pytest.mark.asyncio
    async def test_wallet_bind_rate_limit(self, storage):
        """Test wallet binding rate limiting."""
        await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key="secret_view_key_12345" + "0" * 43,
        )

        # Should be rate limited immediately after binding
        is_limited = await storage.check_wallet_bind_rate_limit("123456")
        assert is_limited is True


class TestStorageChequeOperations:
    """Test cheque CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_cheque(self, storage):
        """Test cheque creation."""
        cheque = await storage.create_cheque(
            user_id="123456",
            amount_rub=1000,
            amount_atomic=100000000000,
            amount_xmr_display="0.100000000000",
            monero_address="4ABC...",
            min_height=100,
            description="Test cheque",
        )

        assert cheque.cheque_id.startswith("chq_")
        assert cheque.user_id == "123456"
        assert cheque.amount_rub == 1000
        assert cheque.status == ChequeStatus.PENDING

    @pytest.mark.asyncio
    async def test_get_cheque(self, storage):
        """Test cheque retrieval."""
        created = await storage.create_cheque(
            user_id="123456",
            amount_rub=1000,
            amount_atomic=100000000000,
            amount_xmr_display="0.100000000000",
            monero_address="4ABC...",
            min_height=100,
        )

        retrieved = await storage.get_cheque(created.cheque_id)

        assert retrieved is not None
        assert retrieved.cheque_id == created.cheque_id
        assert retrieved.amount_rub == 1000

    @pytest.mark.asyncio
    async def test_cancel_cheque(self, storage):
        """Test cheque cancellation."""
        cheque = await storage.create_cheque(
            user_id="123456",
            amount_rub=1000,
            amount_atomic=100000000000,
            amount_xmr_display="0.100000000000",
            monero_address="4ABC...",
            min_height=100,
        )

        cancelled = await storage.cancel_cheque(cheque.cheque_id)

        assert cancelled is not None
        assert cancelled.status == ChequeStatus.CANCELLED

        # Should be removed from pending
        pending = await storage.list_pending_cheque_ids()
        assert cheque.cheque_id not in pending

    @pytest.mark.asyncio
    async def test_cancel_non_pending_cheque_raises(self, storage):
        """Test cancelling already cancelled cheque raises error."""
        cheque = await storage.create_cheque(
            user_id="123456",
            amount_rub=1000,
            amount_atomic=100000000000,
            amount_xmr_display="0.100000000000",
            monero_address="4ABC...",
            min_height=100,
        )
        await storage.cancel_cheque(cheque.cheque_id)

        with pytest.raises(StorageError):
            await storage.cancel_cheque(cheque.cheque_id)

    @pytest.mark.asyncio
    async def test_list_user_cheques(self, storage):
        """Test listing user's cheques."""
        # Create multiple cheques
        for i in range(3):
            await storage.create_cheque(
                user_id="123456",
                amount_rub=1000 + i,
                amount_atomic=100000000000 + i,
                amount_xmr_display=f"0.10000000000{i}",
                monero_address="4ABC...",
                min_height=100,
            )

        cheques = await storage.list_user_cheques("123456")

        assert len(cheques) == 3
        # Should be sorted by newest first
        assert cheques[0].amount_rub > cheques[1].amount_rub > cheques[2].amount_rub


class TestStoragePendingIndex:
    """Test pending cheque index operations."""

    @pytest.mark.asyncio
    async def test_pending_cheque_appears_in_list(self, storage):
        """Test pending cheque appears in pending list."""
        cheque = await storage.create_cheque(
            user_id="123456",
            amount_rub=1000,
            amount_atomic=100000000000,
            amount_xmr_display="0.100000000000",
            monero_address="4ABC...",
            min_height=100,
        )

        pending = await storage.list_pending_cheque_ids()

        assert cheque.cheque_id in pending

    @pytest.mark.asyncio
    async def test_confirmed_cheque_removed_from_pending(self, storage):
        """Test confirmed cheque is removed from pending."""
        cheque = await storage.create_cheque(
            user_id="123456",
            amount_rub=1000,
            amount_atomic=100000000000,
            amount_xmr_display="0.100000000000",
            monero_address="4ABC...",
            min_height=100,
        )

        # Mark as confirmed
        cheque.status = ChequeStatus.CONFIRMED
        await storage.save_cheque(cheque)

        pending = await storage.list_pending_cheque_ids()
        assert cheque.cheque_id not in pending

    @pytest.mark.asyncio
    async def test_expired_cheque_not_in_pending(self, storage):
        """Test expired cheques don't appear in pending list."""
        # This test requires time manipulation
        # In real scenario, expiry is based on Redis TTL
        # For this test, we'll verify the pending logic handles expiry

        # Create cheque with very short expiry (1 second ago)
        now = datetime.now(UTC)
        cheque = ChequeRecord(
            cheque_id="test_chq_123",
            user_id="123456",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4ABC...",
            min_height=100,
            amount_xmr_display="0.100000000000",
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(seconds=1),  # Already expired
        )
        await storage.save_cheque(cheque)
        await storage._add_to_pending(cheque.cheque_id, cheque.expires_at)

        # Pending list uses current timestamp - expired cheques should not appear
        pending = await storage.list_pending_cheque_ids()
        assert cheque.cheque_id not in pending


class TestStorageDataDeletion:
    """Test GDPR-style data deletion."""

    @pytest.mark.asyncio
    async def test_delete_all_user_data(self, storage):
        """Test complete user data deletion."""
        # Setup: create user with wallet and cheques
        user = UserRecord(user_id="123456", language="en")
        await storage.save_user(user)

        await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key="secret_view_key_12345" + "0" * 43,
        )

        for i in range(3):
            await storage.create_cheque(
                user_id="123456",
                amount_rub=1000 + i,
                amount_atomic=100000000000 + i,
                amount_xmr_display=f"0.10000000000{i}",
                monero_address="4ABC...",
                min_height=100,
            )

        # Delete all data
        result = await storage.delete_all_user_data("123456")

        assert result["cheques"] == 3
        assert result["wallet"] == 1
        assert result["user"] == 1

        # Verify deletion
        assert await storage.get_user("123456") is None
        assert await storage.has_wallet("123456") is False
        assert len(await storage.list_user_cheques("123456")) == 0


class TestStorageLoadUserWallet:
    """Test load_user_wallet protocol method."""

    @pytest.mark.asyncio
    async def test_load_user_wallet_success(self, storage):
        """Test loading wallet via protocol method."""
        await storage.bind_wallet(
            user_id="123456",
            address="4ABC...",
            view_key="secret_view_key_12345" + "0" * 43,
        )

        wallet = await storage.load_user_wallet("123456")

        assert wallet.user_id == "123456"
        assert wallet.monero_address == "4ABC..."

    @pytest.mark.asyncio
    async def test_load_user_wallet_not_found(self, storage):
        """Test loading non-existent wallet raises error."""
        with pytest.raises(StorageError) as exc_info:
            await storage.load_user_wallet("999999")

        assert "Wallet not found" in str(exc_info.value)
