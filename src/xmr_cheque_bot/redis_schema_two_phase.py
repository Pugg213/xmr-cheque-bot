"""Updated Redis schema for two-phase cheque system.

This module defines new data structures for:
- ChequeOffer: Long-lived offer (30 min), no XMR amount at creation
- Invoice: Short-lived payment request (15 min), XMR computed at generation time

Compatible with existing ChequeRecord for backward compatibility during migration.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Self


class OfferStatus(StrEnum):
    """Status of a ChequeOffer."""

    PENDING = "pending"  # Created, waiting for payer
    CANCELLED = "cancelled"  # Seller cancelled
    COMPLETED = "completed"  # Invoice paid and confirmed


class InvoiceStatus(StrEnum):
    """Status of an Invoice."""

    AWAITING_PAYMENT = "awaiting_payment"  # Generated, waiting for payment
    PAID = "paid"  # Payment detected and confirmed
    EXPIRED = "expired"  # 15 min TTL exceeded
    CANCELLED = "cancelled"  # Replaced by newer invoice or offer cancelled


# =============================================================================
# TTL Configuration (Two-phase)
# =============================================================================

OFFER_TTL_SECONDS = 1800  # 30 minutes for ChequeOffer
INVOICE_TTL_SECONDS = 900  # 15 minutes for Invoice


# =============================================================================
# Redis Key Patterns (Two-phase)
# =============================================================================


class TwoPhaseRedisKeys:
    """Redis key patterns for two-phase cheque system.

    Uses separate prefixes to avoid collisions with legacy ChequeRecord.
    """

    # Offer data
    CHEQUE_OFFER = "offer:{offer_id}"

    # Invoice data
    INVOICE = "invoice:{invoice_id}"

    # Indices
    PENDING_OFFERS = "pending_offers"
    PENDING_INVOICES = "pending_invoices"

    # User indices
    USER_OFFERS_INDEX = "user_offers:{user_id}"

    @classmethod
    def offer(cls, offer_id: str) -> str:
        """Get Redis key for ChequeOffer record."""
        return cls.CHEQUE_OFFER.format(offer_id=offer_id)

    @classmethod
    def invoice(cls, invoice_id: str) -> str:
        """Get Redis key for Invoice record."""
        return cls.INVOICE.format(invoice_id=invoice_id)

    @classmethod
    def user_offers_index(cls, user_id: str) -> str:
        """Get Redis key for user's offer index (sorted set)."""
        return cls.USER_OFFERS_INDEX.format(user_id=user_id)


# =============================================================================
# Data Classes (Two-phase)
# =============================================================================


@dataclass
class ChequeOffer:
    """Phase 1: Seller creates an offer to receive RUB.

    - Long-lived: 30 minutes
    - No XMR amount stored (computed at Invoice generation time)
    - Can have multiple Invoices (one active at a time)
    """

    # Identification
    offer_id: str
    seller_user_id: str

    # Amount specification (RUB only at this stage)
    amount_rub: int
    description: str = ""
    recipient_address: str = ""  # Seller's XMR address

    # Status tracking
    status: OfferStatus = OfferStatus.PENDING

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(seconds=OFFER_TTL_SECONDS))

    # Current active invoice (if any)
    current_invoice_id: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "offer_id": self.offer_id,
            "seller_user_id": self.seller_user_id,
            "amount_rub": str(self.amount_rub),
            "description": self.description,
            "recipient_address": self.recipient_address,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "current_invoice_id": self.current_invoice_id or "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary retrieved from Redis."""
        return cls(
            offer_id=data["offer_id"],
            seller_user_id=data["seller_user_id"],
            amount_rub=int(data["amount_rub"]),
            description=data.get("description", ""),
            recipient_address=data.get("recipient_address", ""),
            status=OfferStatus(data.get("status", "pending")),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            current_invoice_id=data.get("current_invoice_id") or None,
        )

    def is_expired(self) -> bool:
        """Check if the offer has expired."""
        return datetime.now(UTC) > self.expires_at

    def is_final(self) -> bool:
        """Check if the offer is in a final state."""
        return self.status in (OfferStatus.COMPLETED, OfferStatus.CANCELLED)


@dataclass
class Invoice:
    """Phase 2: Payment request generated when payer clicks "Pay".

    - Short-lived: 15 minutes
    - XMR amount computed at generation time using current rate
    - Rate is snapshot and stored for reference
    """

    # Identification
    invoice_id: str
    cheque_offer_id: str  # Parent offer

    # Amount specification (computed at generation time)
    amount_xmr: str  # Decimal as string for precision
    amount_atomic_expected: int  # Exact atomic units (base + tail)
    tail: int  # Unique tail (1..9999)

    # Anti-replay / collision guard
    # Do not match transfers below this height (mempool height=0 is allowed).
    min_height: int = 0

    # Rate snapshot at generation time
    rate_xmr_rub: str  # Decimal as string

    # Status tracking
    status: InvoiceStatus = InvoiceStatus.AWAITING_PAYMENT

    # Timestamps
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC) + timedelta(seconds=INVOICE_TTL_SECONDS))

    # Payment tracking (filled when detected)
    tx_hash: str | None = None
    tx_height: int | None = None
    confirmations: int = 0
    paid_at: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for Redis storage."""
        return {
            "invoice_id": self.invoice_id,
            "cheque_offer_id": self.cheque_offer_id,
            "amount_xmr": self.amount_xmr,
            "amount_atomic_expected": str(self.amount_atomic_expected),
            "tail": str(self.tail),
            "min_height": str(self.min_height),
            "rate_xmr_rub": self.rate_xmr_rub,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "tx_hash": self.tx_hash or "",
            "tx_height": str(self.tx_height) if self.tx_height else "",
            "confirmations": str(self.confirmations),
            "paid_at": self.paid_at.isoformat() if self.paid_at else "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        """Create from dictionary retrieved from Redis."""
        return cls(
            invoice_id=data["invoice_id"],
            cheque_offer_id=data["cheque_offer_id"],
            amount_xmr=data["amount_xmr"],
            amount_atomic_expected=int(data["amount_atomic_expected"]),
            tail=int(data["tail"]),
            min_height=int(data.get("min_height", 0) or 0),
            rate_xmr_rub=data["rate_xmr_rub"],
            status=InvoiceStatus(data.get("status", "awaiting_payment")),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            tx_hash=data.get("tx_hash") or None,
            tx_height=int(data["tx_height"]) if data.get("tx_height") else None,
            confirmations=int(data.get("confirmations", 0)),
            paid_at=datetime.fromisoformat(data["paid_at"]) if data.get("paid_at") else None,
        )

    def is_expired(self) -> bool:
        """Check if the invoice has expired."""
        return datetime.now(UTC) > self.expires_at

    def is_final(self) -> bool:
        """Check if the invoice is in a final state."""
        return self.status in (InvoiceStatus.PAID, InvoiceStatus.EXPIRED, InvoiceStatus.CANCELLED)


# =============================================================================
# Helper Functions
# =============================================================================


def generate_offer_id() -> str:
    """Generate unique offer ID."""
    import uuid

    return f"off_{uuid.uuid4().hex[:16]}"


def generate_invoice_id() -> str:
    """Generate unique invoice ID."""
    import uuid

    return f"inv_{uuid.uuid4().hex[:16]}"
