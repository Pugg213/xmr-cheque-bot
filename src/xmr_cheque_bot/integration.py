"""Integration module for two-phase cheque system.

This module provides a clean integration point between:
- Legacy ChequeRecord system (for backward compatibility)
- New two-phase system (ChequeOffer + Invoice)

Migration path:
1. Deploy two-phase code alongside legacy
2. New cheques use two-phase APIs
3. Legacy monitor continues for old cheques
4. New monitor handles invoices
5. Eventually deprecate legacy
"""

from __future__ import annotations

import structlog

from xmr_cheque_bot.storage import RedisStorage
from xmr_cheque_bot.storage_two_phase import TwoPhaseStorage
from xmr_cheque_bot.redis_schema import ChequeRecord, ChequeStatus
from xmr_cheque_bot.redis_schema_two_phase import (
    ChequeOffer,
    Invoice,
    OfferStatus,
    InvoiceStatus,
)

logger = structlog.get_logger()


class HybridStorage:
    """Hybrid storage supporting both legacy and two-phase systems.

    Provides unified interface for gradual migration.
    """

    def __init__(
        self,
        legacy_storage: RedisStorage | None = None,
        two_phase_storage: TwoPhaseStorage | None = None,
    ) -> None:
        """Initialize hybrid storage.

        Args:
            legacy_storage: Legacy RedisStorage instance
            two_phase_storage: New TwoPhaseStorage instance
        """
        self.legacy = legacy_storage or RedisStorage()
        self.two_phase = two_phase_storage or TwoPhaseStorage()

    async def close(self) -> None:
        """Close both storage connections."""
        await self.legacy.close()
        await self.two_phase.close()

    # ==============================================================================
    # Unified Offer/Cheque Creation
    # ==============================================================================

    async def create_offer_or_cheque(
        self,
        user_id: str,
        amount_rub: int,
        recipient_address: str,
        description: str = "",
        use_two_phase: bool = True,
    ) -> ChequeOffer | ChequeRecord:
        """Create either a two-phase offer or legacy cheque.

        Args:
            user_id: User ID
            amount_rub: Amount in rubles
            recipient_address: XMR address
            description: Optional description
            use_two_phase: If True, create ChequeOffer; else legacy ChequeRecord

        Returns:
            ChequeOffer or ChequeRecord
        """
        if use_two_phase:
            offer = await self.two_phase.create_cheque_offer(
                seller_user_id=user_id,
                amount_rub=amount_rub,
                recipient_address=recipient_address,
                description=description,
            )
            logger.info("hybrid_created_offer", offer_id=offer.offer_id, user_id=user_id)
            return offer
        else:
            # Legacy path - need to compute amount immediately
            from xmr_cheque_bot.amount import compute_cheque_amount
            from xmr_cheque_bot.config import get_settings

            computed = await compute_cheque_amount(amount_rub)

            # Get current height
            settings = get_settings()
            min_height = 0  # Simplified - in real code would fetch height

            cheque = await self.legacy.create_cheque(
                user_id=user_id,
                amount_rub=amount_rub,
                amount_atomic=computed.amount_atomic_expected,
                amount_xmr_display=computed.amount_xmr_display,
                monero_address=recipient_address,
                min_height=min_height,
                description=description,
            )
            logger.info("hybrid_created_legacy_cheque", cheque_id=cheque.cheque_id, user_id=user_id)
            return cheque

    # ==============================================================================
    # Unified Query Interface
    # ==============================================================================

    async def get_any(
        self,
        id_str: str,
    ) -> ChequeOffer | Invoice | ChequeRecord | None:
        """Get any type of record by ID.

        Tries in order:
        1. Two-phase Invoice
        2. Two-phase ChequeOffer
        3. Legacy ChequeRecord

        Args:
            id_str: ID string (prefix determines type)

        Returns:
            Found record or None
        """
        # Try two-phase first
        if id_str.startswith("inv_"):
            return await self.two_phase.get_invoice(id_str)

        if id_str.startswith("off_"):
            return await self.two_phase.get_offer(id_str)

        # Try legacy
        if id_str.startswith("chq_"):
            return await self.legacy.get_cheque(id_str)

        # Unknown prefix - try all
        if (inv := await self.two_phase.get_invoice(id_str)):
            return inv
        if (off := await self.two_phase.get_offer(id_str)):
            return off
        if (chq := await self.legacy.get_cheque(id_str)):
            return chq

        return None

    async def list_all_pending(self) -> list:
        """List all pending items from both systems.

        Returns:
            Combined list of pending offers, invoices, and legacy cheques
        """
        # Get two-phase pending invoices
        invoices = await self.two_phase.list_pending_invoices()

        # Get legacy pending cheques
        legacy_ids = await self.legacy.list_pending_cheque_ids()
        legacy_cheques = await self.legacy.load_cheques(legacy_ids)

        return invoices + legacy_cheques


# ==============================================================================
# Feature Flags
# ==============================================================================

class TwoPhaseFeatureFlags:
    """Feature flags for gradual rollout."""

    def __init__(self) -> None:
        self._two_phase_creation = True
        self._two_phase_monitor = True
        self._legacy_monitor = True

    @property
    def two_phase_creation(self) -> bool:
        """Use two-phase for new cheque creation."""
        return self._two_phase_creation

    @two_phase_creation.setter
    def two_phase_creation(self, value: bool) -> None:
        self._two_phase_creation = value

    @property
    def two_phase_monitor(self) -> bool:
        """Enable two-phase payment monitor."""
        return self._two_phase_monitor

    @two_phase_monitor.setter
    def two_phase_monitor(self, value: bool) -> None:
        self._two_phase_monitor = value

    @property
    def legacy_monitor(self) -> bool:
        """Keep legacy monitor running for old cheques."""
        return self._legacy_monitor

    @legacy_monitor.setter
    def legacy_monitor(self, value: bool) -> None:
        self._legacy_monitor = value


# Global feature flags instance
feature_flags = TwoPhaseFeatureFlags()
