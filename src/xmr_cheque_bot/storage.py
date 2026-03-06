"""Async Redis storage implementation for XMR Cheque Bot.

Implements the Storage protocol for payment_monitor and provides
user/cheque/wallet management with proper TTL handling.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
import structlog

from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.encryption import EncryptionManager, create_encryption_manager
from xmr_cheque_bot.redis_schema import (
    ChequeRecord,
    ChequeStatus,
    RedisKeys,
    TTLConfig,
    UserRecord,
    UserWallet,
    get_cheque_ttl,
)

logger = structlog.get_logger()


class StorageError(Exception):
    """Raised when storage operation fails."""

    pass


class RedisStorage:
    """Async Redis storage implementation.

    Implements the Storage protocol from payment_monitor plus
    additional methods for user and wallet management.
    """

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        encryption: EncryptionManager | None = None,
    ) -> None:
        """Initialize Redis storage.

        Args:
            redis_client: Optional Redis client (creates from settings if None)
            encryption: Optional encryption manager (creates from settings if None)
        """
        self._redis = redis_client
        self._encryption = encryption
        self._ttl_config = TTLConfig()
        self._own_redis = redis_client is None

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    def _get_encryption(self) -> EncryptionManager:
        """Get or create encryption manager."""
        if self._encryption is None:
            self._encryption = create_encryption_manager()
        return self._encryption

    async def close(self) -> None:
        """Close Redis connection if we own it."""
        if self._own_redis and self._redis is not None:
            await self._redis.close()
            self._redis = None

    async def _hset_dict(self, key: str, data: dict[str, Any], ttl: int | None = None) -> None:
        """Store dictionary as Redis hash."""
        r = await self._get_redis()
        # Filter out None values and convert to strings
        clean_data = {k: str(v) if v is not None else "" for k, v in data.items()}
        await r.hset(key, mapping=clean_data)
        if ttl is not None and ttl > 0:
            await r.expire(key, ttl)

    async def _hget_dict(self, key: str) -> dict[str, str] | None:
        """Get dictionary from Redis hash."""
        r = await self._get_redis()
        data = await r.hgetall(key)
        if not data:
            return None
        return dict(data)

    # ======================================================================
    # User Methods
    # ======================================================================

    async def get_user(self, user_id: str) -> UserRecord | None:
        """Get user record by ID.

        Args:
            user_id: Telegram user ID

        Returns:
            UserRecord or None if not found
        """
        key = RedisKeys.user(user_id)
        data = await self._hget_dict(key)
        if data is None:
            return None
        return UserRecord.from_dict(data)

    async def save_user(self, user: UserRecord) -> None:
        """Save user record.

        Args:
            user: UserRecord to save
        """
        key = RedisKeys.user(user.user_id)
        await self._hset_dict(key, user.to_dict())
        logger.debug("user_saved", user_id=user.user_id, language=user.language)

    async def get_or_create_user(self, user_id: str, language: str = "en") -> UserRecord:
        """Get existing user or create new one.

        Args:
            user_id: Telegram user ID
            language: Default language if new user

        Returns:
            UserRecord (existing or newly created)
        """
        user = await self.get_user(user_id)
        if user is None:
            user = UserRecord(user_id=user_id, language=language)
            await self.save_user(user)
            logger.info("user_created", user_id=user_id, language=language)
        return user

    async def update_user_activity(self, user_id: str) -> None:
        """Update user's last activity timestamp.

        Args:
            user_id: Telegram user ID
        """
        user = await self.get_user(user_id)
        if user is not None:
            user.last_activity_at = datetime.now(UTC)
            await self.save_user(user)

    # ======================================================================
    # Wallet Methods
    # ======================================================================

    async def get_wallet(self, user_id: str) -> UserWallet | None:
        """Get user's wallet.

        Args:
            user_id: Telegram user ID

        Returns:
            UserWallet or None if not bound
        """
        key = RedisKeys.user_wallet(user_id)
        data = await self._hget_dict(key)
        if data is None:
            return None
        return UserWallet.from_dict(data)

    async def has_wallet(self, user_id: str) -> bool:
        """Check if user has bound wallet.

        Args:
            user_id: Telegram user ID

        Returns:
            True if wallet exists
        """
        wallet = await self.get_wallet(user_id)
        return wallet is not None

    async def bind_wallet(
        self,
        user_id: str,
        address: str,
        view_key: str,
        wallet_file_name: str | None = None,
        wallet_password: str | None = None,
    ) -> UserWallet:
        """Bind wallet to user.

        Args:
            user_id: Telegram user ID
            address: Monero address
            view_key: Private view key (will be encrypted)
            wallet_file_name: Optional wallet file name

        Returns:
            Created UserWallet
        """
        encryption = self._get_encryption()
        import secrets

        encrypted_view_key = encryption.encrypt(view_key)

        # If password is not provided, generate one. IMPORTANT: callers that
        # create wallet files must pass the same password to the wallet RPC.
        if wallet_password is None:
            wallet_password = secrets.token_urlsafe(18)

        encrypted_wallet_password = encryption.encrypt(wallet_password)

        wallet = UserWallet(
            user_id=user_id,
            monero_address=address,
            encrypted_view_key=encrypted_view_key,
            encrypted_wallet_password=encrypted_wallet_password,
            wallet_file_name=wallet_file_name,
        )

        key = RedisKeys.user_wallet(user_id)
        await self._hset_dict(key, wallet.to_dict())

        # Set rate limit
        rate_limit_key = RedisKeys.rate_limit_wallet_bind(user_id)
        r = await self._get_redis()
        await r.setex(rate_limit_key, self._ttl_config.RATE_LIMIT_WALLET_BIND_SECONDS, "1")

        logger.info("wallet_bound", user_id=user_id, address_prefix=address[:8])
        return wallet

    async def unbind_wallet(self, user_id: str) -> bool:
        """Remove wallet binding.

        Args:
            user_id: Telegram user ID

        Returns:
            True if wallet was removed, False if not found
        """
        key = RedisKeys.user_wallet(user_id)
        r = await self._get_redis()
        result = await r.delete(key)
        logger.info("wallet_unbound", user_id=user_id, existed=result > 0)
        return result > 0

    async def decrypt_view_key(self, wallet: UserWallet) -> str:
        """Decrypt view key from wallet.

        Args:
            wallet: UserWallet with encrypted view key

        Returns:
            Decrypted view key
        """
        encryption = self._get_encryption()
        return encryption.decrypt(wallet.encrypted_view_key)

    async def decrypt_wallet_password(self, wallet: UserWallet) -> str:
        """Decrypt wallet file password."""
        encryption = self._get_encryption()
        return encryption.decrypt(wallet.encrypted_wallet_password)

    async def check_wallet_bind_rate_limit(self, user_id: str) -> bool:
        """Check if user is rate limited for wallet binding.

        Args:
            user_id: Telegram user ID

        Returns:
            True if rate limited
        """
        key = RedisKeys.rate_limit_wallet_bind(user_id)
        r = await self._get_redis()
        return await r.exists(key) > 0

    # ======================================================================
    # Cheque Methods
    # ======================================================================

    def _generate_cheque_id(self) -> str:
        """Generate unique cheque ID."""
        return f"chq_{uuid.uuid4().hex[:16]}"

    async def create_cheque(
        self,
        user_id: str,
        amount_rub: int,
        amount_atomic: int,
        amount_xmr_display: str,
        monero_address: str,
        min_height: int,
        description: str = "",
    ) -> ChequeRecord:
        """Create new cheque.

        Args:
            user_id: Telegram user ID
            amount_rub: Amount in RUB
            amount_atomic: Amount in atomic units
            amount_xmr_display: Human-readable XMR amount
            monero_address: Destination address
            min_height: Minimum block height
            description: Optional description

        Returns:
            Created ChequeRecord
        """
        cheque_id = self._generate_cheque_id()

        cheque = ChequeRecord(
            cheque_id=cheque_id,
            user_id=user_id,
            amount_rub=amount_rub,
            amount_atomic_expected=amount_atomic,
            monero_address=monero_address,
            min_height=min_height,
            amount_xmr_display=amount_xmr_display,
            description=description,
        )

        await self.save_cheque(cheque)

        # Add to user's cheque index
        await self._add_to_user_cheques(user_id, cheque_id)

        # Add to pending index with expiry timestamp as score
        await self._add_to_pending(cheque_id, cheque.expires_at)

        # Set rate limit
        rate_limit_key = RedisKeys.rate_limit_cheque(user_id)
        r = await self._get_redis()
        await r.setex(rate_limit_key, self._ttl_config.RATE_LIMIT_CHEQUE_SECONDS, "1")

        logger.info(
            "cheque_created",
            cheque_id=cheque_id,
            user_id=user_id,
            amount_rub=amount_rub,
        )

        return cheque

    async def get_cheque(self, cheque_id: str) -> ChequeRecord | None:
        """Get cheque by ID.

        Args:
            cheque_id: Cheque ID

        Returns:
            ChequeRecord or None if not found
        """
        key = RedisKeys.cheque(cheque_id)
        data = await self._hget_dict(key)
        if data is None:
            return None
        return ChequeRecord.from_dict(data)

    async def save_cheque(self, cheque: ChequeRecord) -> None:
        """Save cheque record with appropriate TTL.

        Args:
            cheque: ChequeRecord to save
        """
        key = RedisKeys.cheque(cheque.cheque_id)
        ttl = get_cheque_ttl(cheque.status, self._ttl_config)
        await self._hset_dict(key, cheque.to_dict(), ttl=ttl)

        # If status changed to final, remove from pending
        if cheque.is_final():
            await self.remove_from_pending(cheque.cheque_id)

    async def cancel_cheque(self, cheque_id: str) -> ChequeRecord | None:
        """Cancel a pending cheque.

        Args:
            cheque_id: Cheque ID

        Returns:
            Updated ChequeRecord or None if not found

        Raises:
            StorageError: If cheque is not in pending state
        """
        cheque = await self.get_cheque(cheque_id)
        if cheque is None:
            return None

        if cheque.status != ChequeStatus.PENDING:
            raise StorageError(f"Cannot cancel cheque with status: {cheque.status}")

        cheque.status = ChequeStatus.CANCELLED
        await self.save_cheque(cheque)
        await self.remove_from_pending(cheque_id)

        logger.info("cheque_cancelled", cheque_id=cheque_id, user_id=cheque.user_id)
        return cheque

    async def delete_cheque(self, user_id: str, cheque_id: str) -> bool:
        """Delete a cheque from user's history/index.

        Notes:
        - This does NOT affect any on-chain funds; it only removes local tracking.
        - Only the owner can delete.

        Returns:
            True if deleted, False if not found / not owned by user.
        """
        cheque = await self.get_cheque(cheque_id)
        if cheque is None or cheque.user_id != user_id:
            return False

        r = await self._get_redis()

        # Remove the cheque record
        await r.delete(RedisKeys.cheque(cheque_id))

        # Remove from indices
        await r.zrem(RedisKeys.user_cheques_index(user_id), cheque_id)
        await r.zrem(RedisKeys.PENDING_CHEQUES, cheque_id)

        logger.info("cheque_deleted", cheque_id=cheque_id, user_id=user_id)
        return True

    async def list_user_cheques(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChequeRecord]:
        """List user's cheques (most recent first).

        Args:
            user_id: Telegram user ID
            limit: Maximum number to return
            offset: Offset for pagination

        Returns:
            List of ChequeRecords
        """
        index_key = RedisKeys.user_cheques_index(user_id)
        r = await self._get_redis()

        # Get cheque IDs from sorted set (reverse order for newest first)
        cheque_ids = await r.zrevrange(index_key, offset, offset + limit - 1)

        return await self.load_cheques(cheque_ids)

    async def count_user_cheques(self, user_id: str) -> int:
        """Count total cheques for user.

        Args:
            user_id: Telegram user ID

        Returns:
            Number of cheques
        """
        index_key = RedisKeys.user_cheques_index(user_id)
        r = await self._get_redis()
        return await r.zcard(index_key)

    async def count_active_cheques(self, user_id: str) -> int:
        """Count active (non-final) cheques for user.

        Args:
            user_id: Telegram user ID

        Returns:
            Number of active cheques
        """
        # This is an approximation - load recent and filter
        cheques = await self.list_user_cheques(user_id, limit=50)
        return sum(1 for c in cheques if not c.is_final())

    # ======================================================================
    # Storage Protocol Implementation (for payment_monitor)
    # ======================================================================

    async def list_pending_cheque_ids(self) -> list[str]:
        """List IDs of pending cheques (not expired).

        Returns:
            List of cheque IDs that need monitoring
        """
        r = await self._get_redis()
        now = datetime.now(UTC).timestamp()

        # Get cheques with expiry > now from sorted set
        cheque_ids = await r.zrangebyscore(
            RedisKeys.PENDING_CHEQUES,
            now,
            "+inf",
        )
        return list(cheque_ids)

    async def load_cheques(self, cheque_ids: list[str]) -> list[ChequeRecord]:
        """Load multiple cheques by ID.

        Args:
            cheque_ids: List of cheque IDs

        Returns:
            List of ChequeRecords (missing ones skipped)
        """
        cheques = []
        for cid in cheque_ids:
            cheque = await self.get_cheque(cid)
            if cheque is not None:
                cheques.append(cheque)
        return cheques

    async def load_user_wallet(self, user_id: str) -> UserWallet:
        """Load user wallet (Storage protocol method).

        Args:
            user_id: Telegram user ID

        Returns:
            UserWallet

        Raises:
            StorageError: If wallet not found
        """
        wallet = await self.get_wallet(user_id)
        if wallet is None:
            raise StorageError(f"Wallet not found for user: {user_id}")
        return wallet

    async def remove_from_pending(self, cheque_id: str) -> None:
        """Remove cheque from pending index.

        Args:
            cheque_id: Cheque ID to remove
        """
        r = await self._get_redis()
        await r.zrem(RedisKeys.PENDING_CHEQUES, cheque_id)

    # ======================================================================
    # Index Management
    # ======================================================================

    async def _add_to_user_cheques(self, user_id: str, cheque_id: str) -> None:
        """Add cheque to user's index."""
        index_key = RedisKeys.user_cheques_index(user_id)
        r = await self._get_redis()
        # Use timestamp as score for time-based ordering
        score = datetime.now(UTC).timestamp()
        await r.zadd(index_key, {cheque_id: score})

    async def _add_to_pending(self, cheque_id: str, expires_at: datetime | None) -> None:
        """Add cheque to pending index with expiry timestamp as score."""
        if expires_at is None:
            return
        r = await self._get_redis()
        score = expires_at.timestamp()
        await r.zadd(RedisKeys.PENDING_CHEQUES, {cheque_id: score})

    # ======================================================================
    # Rate Limiting
    # ======================================================================

    async def check_cheque_rate_limit(self, user_id: str) -> bool:
        """Check if user is rate limited for cheque creation.

        Args:
            user_id: Telegram user ID

        Returns:
            True if rate limited
        """
        key = RedisKeys.rate_limit_cheque(user_id)
        r = await self._get_redis()
        return await r.exists(key) > 0

    # ======================================================================
    # Data Deletion
    # ======================================================================

    async def delete_all_user_data(self, user_id: str) -> dict[str, int]:
        """Delete all data for a user (GDPR-style right to deletion).

        Args:
            user_id: Telegram user ID

        Returns:
            Dict with counts of deleted items
        """
        r = await self._get_redis()
        deleted = {"cheques": 0, "indices": 0, "wallet": 0, "user": 0}

        # Get user's cheque IDs
        index_key = RedisKeys.user_cheques_index(user_id)
        cheque_ids = await r.zrange(index_key, 0, -1)

        # Delete each cheque
        for cid in cheque_ids:
            await r.delete(RedisKeys.cheque(cid))
            await self.remove_from_pending(cid)
            deleted["cheques"] += 1

        # Delete indices
        await r.delete(index_key)
        await r.delete(RedisKeys.rate_limit_cheque(user_id))
        await r.delete(RedisKeys.rate_limit_wallet_bind(user_id))
        deleted["indices"] += 3

        # Delete wallet
        wallet_deleted = await r.delete(RedisKeys.user_wallet(user_id))
        if wallet_deleted:
            deleted["wallet"] = 1

        # Delete user record
        user_deleted = await r.delete(RedisKeys.user(user_id))
        if user_deleted:
            deleted["user"] = 1

        logger.info("user_data_deleted", user_id=user_id, **deleted)
        return deleted
