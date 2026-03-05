"""Redis schema definitions for XMR Cheque Bot.

This module defines all Redis keys, data structures, and TTL management
for the application. All interactions with Redis should use these helpers
to ensure consistency.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Self


class ChequeStatus(StrEnum):
    """Status of a payment cheque."""
    PENDING = "pending"       # Created, no tx found
    MEMPOOL = "mempool"       # Tx found in mempool (0 conf)
    CONFIRMING = "confirming" # 1..5 confirmations
    CONFIRMED = "confirmed"   # >=6 confirmations (final)
    EXPIRED = "expired"       # TTL exceeded, not paid
    CANCELLED = "cancelled"   # User cancelled a pending cheque


# =============================================================================
# Redis Key Patterns
# =============================================================================

class RedisKeys:
    """Redis key patterns and generators.
    
    All keys are organized under prefixes for easy scanning and management.
    """
    
    # User data
    USER = "user:{user_id}"
    USER_WALLET = "user:{user_id}:wallet"
    USER_CHEQUES_INDEX = "user_cheques:{user_id}"
    
    # Cheque data
    CHEQUE = "cheque:{cheque_id}"
    
    # Indices
    PENDING_CHEQUES = "pending_cheques"
    
    # Rate limiting
    RATE_LIMIT_CHEQUE = "ratelimit:cheque:{user_id}"
    RATE_LIMIT_WALLET_BIND = "ratelimit:wallet_bind:{user_id}"
    
    # Metadata
    CHEQUE_COUNTER = "meta:cheque_counter"
    
    @classmethod
    def user(cls, user_id: str | int) -> str:
        """Get Redis key for user record."""
        return cls.USER.format(user_id=user_id)
    
    @classmethod
    def user_wallet(cls, user_id: str | int) -> str:
        """Get Redis key for user wallet data."""
        return cls.USER_WALLET.format(user_id=user_id)
    
    @classmethod
    def user_cheques_index(cls, user_id: str | int) -> str:
        """Get Redis key for user's cheque index (sorted set)."""
        return cls.USER_CHEQUES_INDEX.format(user_id=user_id)
    
    @classmethod
    def cheque(cls, cheque_id: str) -> str:
        """Get Redis key for cheque record."""
        return cls.CHEQUE.format(cheque_id=cheque_id)
    
    @classmethod
    def rate_limit_cheque(cls, user_id: str | int) -> str:
        """Get Redis key for cheque creation rate limit."""
        return cls.RATE_LIMIT_CHEQUE.format(user_id=user_id)
    
    @classmethod
    def rate_limit_wallet_bind(cls, user_id: str | int) -> str:
        """Get Redis key for wallet binding rate limit."""
        return cls.RATE_LIMIT_WALLET_BIND.format(user_id=user_id)


# =============================================================================
# TTL Configuration
# =============================================================================

@dataclass(frozen=True)
class TTLConfig:
    """TTL (Time To Live) configuration for Redis keys."""
    
    # Cheque TTL - how long a cheque remains valid
    CHEQUE_PENDING_SECONDS: int = 3600  # 1 hour
    
    # Rate limit windows
    RATE_LIMIT_CHEQUE_SECONDS: int = 600  # 10 minutes
    RATE_LIMIT_WALLET_BIND_SECONDS: int = 600  # 10 minutes
    
    # Completed cheque retention (minimal history)
    COMPLETED_CHEQUE_RETENTION_DAYS: int = 7
    
    @classmethod
    def from_settings(cls) -> Self:
        """Create TTLConfig from application settings."""
        from xmr_cheque_bot.config import get_settings
        settings = get_settings()
        return cls(
            CHEQUE_PENDING_SECONDS=settings.cheque_ttl_seconds,
            RATE_LIMIT_CHEQUE_SECONDS=600,
            RATE_LIMIT_WALLET_BIND_SECONDS=600,
            COMPLETED_CHEQUE_RETENTION_DAYS=7,
        )


def get_cheque_ttl(status: ChequeStatus, config: TTLConfig | None = None) -> int:
    """Get appropriate TTL for a cheque based on its status.
    
    Args:
        status: Current cheque status
        config: Optional TTLConfig (uses default if not provided)
    
    Returns:
        TTL in seconds for the Redis key
    """
    if config is None:
        config = TTLConfig()
    
    match status:
        case ChequeStatus.PENDING:
            return config.CHEQUE_PENDING_SECONDS
        case ChequeStatus.MEMPOOL | ChequeStatus.CONFIRMING:
            # Keep longer while in progress
            return config.CHEQUE_PENDING_SECONDS + 3600
        case ChequeStatus.CONFIRMED | ChequeStatus.EXPIRED | ChequeStatus.CANCELLED:
            # Completed cheques: keep minimal history
            return config.COMPLETED_CHEQUE_RETENTION_DAYS * 86400
        case _:
            return config.CHEQUE_PENDING_SECONDS


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class UserWallet:
    """User's linked Monero wallet information.
    
    View key is stored encrypted. This is the minimum required
    to monitor incoming transactions.
    """
    
    user_id: str
    monero_address: str
    encrypted_view_key: str  # Fernet-encrypted private view key
    encrypted_wallet_password: str  # Fernet-encrypted wallet file password
    wallet_file_name: str | None = None  # Name of wallet file in wallet dir
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "user_id": self.user_id,
            "monero_address": self.monero_address,
            "encrypted_view_key": self.encrypted_view_key,
            "encrypted_wallet_password": self.encrypted_wallet_password,
            "wallet_file_name": self.wallet_file_name or "",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary retrieved from Redis."""
        return cls(
            user_id=data["user_id"],
            monero_address=data["monero_address"],
            encrypted_view_key=data["encrypted_view_key"],
            encrypted_wallet_password=data.get("encrypted_wallet_password", ""),
            wallet_file_name=data.get("wallet_file_name") or None,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


@dataclass
class ChequeRecord:
    """Payment cheque record.
    
    Core fields for cheque tracking and payment monitoring.
    The unique tail mechanism ensures no amount collisions.
    """
    
    # Identification
    cheque_id: str
    user_id: str
    
    # Amount specification (exact match required)
    amount_rub: int  # Original amount in rubles (for display)
    amount_atomic_expected: int  # Exact atomic units expected (base + tail)
    
    # Payment tracking
    monero_address: str  # Destination address
    min_height: int  # Block height at creation (for tx filtering)
    status: ChequeStatus = ChequeStatus.PENDING
    
    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime | None = None
    paid_at: datetime | None = None
    
    # Transaction details (filled when detected)
    tx_hash: str | None = None
    tx_height: int | None = None
    confirmations: int = 0
    
    # Display fields
    amount_xmr_display: str = ""  # Human-readable XMR amount
    description: str = ""  # Optional description
    
    def __post_init__(self) -> None:
        """Set expires_at if not provided."""
        if self.expires_at is None:
            from xmr_cheque_bot.config import get_settings
            settings = get_settings()
            self.expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.cheque_ttl_seconds)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "cheque_id": self.cheque_id,
            "user_id": self.user_id,
            "amount_rub": str(self.amount_rub),
            "amount_atomic_expected": str(self.amount_atomic_expected),
            "monero_address": self.monero_address,
            "min_height": str(self.min_height),
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else "",
            "paid_at": self.paid_at.isoformat() if self.paid_at else "",
            "tx_hash": self.tx_hash or "",
            "tx_height": str(self.tx_height) if self.tx_height else "",
            "confirmations": str(self.confirmations),
            "amount_xmr_display": self.amount_xmr_display,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary retrieved from Redis."""
        return cls(
            cheque_id=data["cheque_id"],
            user_id=data["user_id"],
            amount_rub=int(data["amount_rub"]),
            amount_atomic_expected=int(data["amount_atomic_expected"]),
            monero_address=data["monero_address"],
            min_height=int(data["min_height"]),
            status=ChequeStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            paid_at=datetime.fromisoformat(data["paid_at"]) if data.get("paid_at") else None,
            tx_hash=data.get("tx_hash") or None,
            tx_height=int(data["tx_height"]) if data.get("tx_height") else None,
            confirmations=int(data["confirmations"]) if data.get("confirmations") else 0,
            amount_xmr_display=data.get("amount_xmr_display", ""),
            description=data.get("description", ""),
        )
    
    def is_expired(self) -> bool:
        """Check if the cheque has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_final(self) -> bool:
        """Check if the cheque is in a final state."""
        return self.status in (ChequeStatus.CONFIRMED, ChequeStatus.EXPIRED, ChequeStatus.CANCELLED)


@dataclass
class UserRecord:
    """User profile and preferences."""
    
    user_id: str
    language: str = "en"  # "en" or "ru"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "user_id": self.user_id,
            "language": self.language,
            "created_at": self.created_at.isoformat(),
            "last_activity_at": self.last_activity_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary retrieved from Redis."""
        return cls(
            user_id=data["user_id"],
            language=data.get("language", "en"),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_activity_at=datetime.fromisoformat(data["last_activity_at"]),
        )
