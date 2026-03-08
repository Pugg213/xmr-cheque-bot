"""Two-phase storage implementation.

Extends RedisStorage with methods for ChequeOffer and Invoice management.
"""

from __future__ import annotations

import redis.asyncio as redis
import structlog

from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.amount import compute_cheque_amount
from xmr_cheque_bot.storage import RedisStorage, StorageError
from xmr_cheque_bot.redis_schema_two_phase import (
    ChequeOffer,
    Invoice,
    InvoiceStatus,
    OfferStatus,
    TwoPhaseRedisKeys,
    generate_invoice_id,
    generate_offer_id,
    OFFER_TTL_SECONDS,
    INVOICE_TTL_SECONDS,
)

logger = structlog.get_logger()


class TwoPhaseStorageError(Exception):
    """Raised when two-phase storage operation fails."""

    pass


class TwoPhaseStorage(RedisStorage):
    """Extended storage for two-phase cheque system.

    Inherits from RedisStorage for backward compatibility.
    Adds ChequeOffer and Invoice management.
    """

    # ======================================================================
    # ChequeOffer Methods
    # ======================================================================

    async def create_cheque_offer(
        self,
        seller_user_id: str,
        amount_rub: int,
        recipient_address: str,
        description: str = "",
    ) -> ChequeOffer:
        """Create a new ChequeOffer (Phase 1).

        Args:
            seller_user_id: Telegram user ID of seller
            amount_rub: Amount in Russian rubles
            recipient_address: Seller's Monero address
            description: Optional description

        Returns:
            Created ChequeOffer
        """
        offer_id = generate_offer_id()

        offer = ChequeOffer(
            offer_id=offer_id,
            seller_user_id=seller_user_id,
            amount_rub=amount_rub,
            recipient_address=recipient_address,
            description=description,
            status=OfferStatus.PENDING,
        )

        await self._save_offer(offer)

        # Add to user's offer index
        await self._add_to_user_offers(seller_user_id, offer_id)

        # Add to pending offers index
        await self._add_to_pending_offers(offer_id, offer.expires_at)

        logger.info(
            "cheque_offer_created",
            offer_id=offer_id,
            seller_user_id=seller_user_id,
            amount_rub=amount_rub,
        )

        return offer

    async def get_offer(self, offer_id: str) -> ChequeOffer | None:
        """Get ChequeOffer by ID.

        Args:
            offer_id: Offer ID

        Returns:
            ChequeOffer or None if not found
        """
        key = TwoPhaseRedisKeys.offer(offer_id)
        data = await self._hget_dict(key)
        if data is None:
            return None
        return ChequeOffer.from_dict(data)

    async def cancel_offer(self, offer_id: str) -> ChequeOffer | None:
        """Cancel a pending offer.

        Args:
            offer_id: Offer ID

        Returns:
            Updated ChequeOffer or None if not found

        Raises:
            TwoPhaseStorageError: If offer is not in pending state
        """
        offer = await self.get_offer(offer_id)
        if offer is None:
            return None

        if offer.status != OfferStatus.PENDING:
            raise TwoPhaseStorageError(f"Cannot cancel offer with status: {offer.status}")

        # Cancel any active invoice
        if offer.current_invoice_id:
            await self.cancel_invoice(offer.current_invoice_id)

        offer.status = OfferStatus.CANCELLED
        await self._save_offer(offer)
        await self._remove_from_pending_offers(offer_id)

        logger.info("offer_cancelled", offer_id=offer_id, seller_user_id=offer.seller_user_id)
        return offer

    async def complete_offer(self, offer_id: str) -> ChequeOffer | None:
        """Mark offer as completed (when invoice is paid).

        Args:
            offer_id: Offer ID

        Returns:
            Updated ChequeOffer or None if not found
        """
        offer = await self.get_offer(offer_id)
        if offer is None:
            return None

        offer.status = OfferStatus.COMPLETED
        await self._save_offer(offer)
        await self._remove_from_pending_offers(offer_id)

        logger.info("offer_completed", offer_id=offer_id, seller_user_id=offer.seller_user_id)
        return offer

    async def list_user_offers(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ChequeOffer]:
        """List user's offers (most recent first).

        Args:
            user_id: Telegram user ID
            limit: Maximum number to return
            offset: Offset for pagination

        Returns:
            List of ChequeOffers
        """
        index_key = TwoPhaseRedisKeys.user_offers_index(user_id)
        r = await self._get_redis()

        offer_ids = await r.zrevrange(index_key, offset, offset + limit - 1)

        offers = []
        for oid in offer_ids:
            offer = await self.get_offer(oid)
            if offer is not None:
                offers.append(offer)
        return offers

    # ======================================================================
    # Invoice Methods
    # ======================================================================

    async def generate_invoice(
        self,
        offer_id: str,
        min_height: int = 0,
    ) -> Invoice:
        """Generate a new Invoice for an offer (Phase 2).

        This method:
        1. Fetches current XMR/RUB rate
        2. Computes XMR amount
        3. Creates Invoice with 15-min expiry
        4. Updates offer with current_invoice_id

        Args:
            offer_id: Parent ChequeOffer ID
            min_height: Minimum block height for tx filtering

        Returns:
            Created Invoice

        Raises:
            TwoPhaseStorageError: If offer not found, expired, or not pending
        """
        offer = await self.get_offer(offer_id)
        if offer is None:
            raise TwoPhaseStorageError(f"Offer not found: {offer_id}")

        if offer.is_expired():
            raise TwoPhaseStorageError("Offer has expired")

        if offer.status != OfferStatus.PENDING:
            raise TwoPhaseStorageError(f"Offer is not pending: {offer.status}")

        # Cancel any existing invoice for this offer
        if offer.current_invoice_id:
            await self.cancel_invoice(offer.current_invoice_id)

        # Compute amount using current rate
        computed = await compute_cheque_amount(offer.amount_rub)

        invoice_id = generate_invoice_id()

        invoice = Invoice(
            invoice_id=invoice_id,
            cheque_offer_id=offer_id,
            amount_xmr=computed.amount_xmr_display,
            amount_atomic_expected=computed.amount_atomic_expected,
            tail=computed.tail,
            min_height=int(min_height or 0),
            rate_xmr_rub=str(computed.rate_xmr_rub),
            status=InvoiceStatus.AWAITING_PAYMENT,
        )

        await self._save_invoice(invoice)

        # Update offer with current invoice
        offer.current_invoice_id = invoice_id
        await self._save_offer(offer)

        # Add to pending invoices index
        await self._add_to_pending_invoices(invoice_id, invoice.expires_at)

        logger.info(
            "invoice_generated",
            invoice_id=invoice_id,
            offer_id=offer_id,
            amount_xmr=computed.amount_xmr_display,
            rate=computed.rate_xmr_rub,
        )

        return invoice

    async def refresh_invoice(
        self,
        invoice_id: str,
        min_height: int = 0,
    ) -> Invoice:
        """Refresh an expired invoice with a new one.

        Args:
            invoice_id: Expired invoice ID to refresh
            min_height: Minimum block height for tx filtering

        Returns:
            New Invoice with current rate

        Raises:
            TwoPhaseStorageError: If invoice not found or not expired
        """
        old_invoice = await self.get_invoice(invoice_id)
        if old_invoice is None:
            raise TwoPhaseStorageError(f"Invoice not found: {invoice_id}")

        if old_invoice.tx_hash:
            raise TwoPhaseStorageError("Invoice already has a payment in progress and cannot be refreshed")

        if not (old_invoice.status == InvoiceStatus.EXPIRED or old_invoice.is_expired()):
            raise TwoPhaseStorageError("Invoice is not expired")

        # Ensure status is EXPIRED before refresh (UI expects it)
        if old_invoice.status != InvoiceStatus.EXPIRED:
            old_invoice.status = InvoiceStatus.EXPIRED
            await self._save_invoice(old_invoice)

        # Cancel old invoice (replaced by newer one)
        await self.cancel_invoice(invoice_id)

        # Generate new invoice for the same offer
        return await self.generate_invoice(
            offer_id=old_invoice.cheque_offer_id,
            min_height=min_height,
        )

    async def get_invoice(self, invoice_id: str) -> Invoice | None:
        """Get Invoice by ID.

        Args:
            invoice_id: Invoice ID

        Returns:
            Invoice or None if not found
        """
        key = TwoPhaseRedisKeys.invoice(invoice_id)
        data = await self._hget_dict(key)
        if data is None:
            return None
        return Invoice.from_dict(data)

    async def cancel_invoice(self, invoice_id: str) -> Invoice | None:
        """Cancel an invoice.

        Args:
            invoice_id: Invoice ID

        Returns:
            Updated Invoice or None if not found
        """
        invoice = await self.get_invoice(invoice_id)
        if invoice is None:
            return None

        # Paid invoices are immutable
        if invoice.status == InvoiceStatus.PAID:
            return invoice

        invoice.status = InvoiceStatus.CANCELLED
        await self._save_invoice(invoice)
        await self._remove_from_pending_invoices(invoice_id)

        logger.info("invoice_cancelled", invoice_id=invoice_id, offer_id=invoice.cheque_offer_id)
        return invoice

    async def mark_invoice_paid(
        self,
        invoice_id: str,
        tx_hash: str,
        tx_height: int,
        confirmations: int,
    ) -> Invoice | None:
        """Mark invoice as paid.

        Args:
            invoice_id: Invoice ID
            tx_hash: Transaction hash
            tx_height: Block height
            confirmations: Number of confirmations

        Returns:
            Updated Invoice or None if not found
        """
        from datetime import UTC, datetime

        invoice = await self.get_invoice(invoice_id)
        if invoice is None:
            return None

        invoice.status = InvoiceStatus.PAID
        invoice.tx_hash = tx_hash
        invoice.tx_height = tx_height
        invoice.confirmations = confirmations
        invoice.paid_at = datetime.now(UTC)

        await self._save_invoice(invoice)
        await self._remove_from_pending_invoices(invoice_id)

        # Also complete the parent offer
        await self.complete_offer(invoice.cheque_offer_id)

        logger.info(
            "invoice_paid",
            invoice_id=invoice_id,
            tx_hash=tx_hash,
            confirmations=confirmations,
        )

        return invoice

    async def update_invoice_confirmations(
        self,
        invoice_id: str,
        confirmations: int,
    ) -> Invoice | None:
        """Update invoice confirmation count.

        Args:
            invoice_id: Invoice ID
            confirmations: New confirmation count

        Returns:
            Updated Invoice or None if not found
        """
        invoice = await self.get_invoice(invoice_id)
        if invoice is None:
            return None

        invoice.confirmations = confirmations
        await self._save_invoice(invoice)

        return invoice

    async def update_invoice_payment_progress(
        self,
        invoice_id: str,
        tx_hash: str,
        tx_height: int | None,
        confirmations: int,
    ) -> Invoice | None:
        """Update invoice payment fields without marking it PAID.

        Used when payment is in mempool / confirming. Keeps the invoice in the monitoring index.
        """
        invoice = await self.get_invoice(invoice_id)
        if invoice is None:
            return None

        invoice.tx_hash = tx_hash
        invoice.tx_height = int(tx_height) if tx_height is not None and int(tx_height) > 0 else None
        invoice.confirmations = int(confirmations or 0)
        await self._save_invoice(invoice)
        return invoice

    async def list_pending_invoices(self) -> list[Invoice]:
        """List invoices that still need monitoring.

        Includes:
        - awaiting_payment (valid or expired-by-time)
        - expired (for late-payment detection until cancelled/paid)

        Note: we also garbage-collect stale zset entries if the invoice key is missing.
        """
        r = await self._get_redis()

        invoice_ids = await r.zrange(TwoPhaseRedisKeys.PENDING_INVOICES, 0, -1)

        invoices: list[Invoice] = []
        for iid in invoice_ids:
            invoice = await self.get_invoice(iid)
            if invoice is None:
                # stale index entry
                await r.zrem(TwoPhaseRedisKeys.PENDING_INVOICES, iid)
                continue
            if invoice.status in (InvoiceStatus.AWAITING_PAYMENT, InvoiceStatus.EXPIRED):
                invoices.append(invoice)

        return invoices

    async def expire_old_invoices(self) -> list[Invoice]:
        """Mark invoices as expired when their UI TTL passes.

        Important:
        - We only expire invoices with **no detected payment** (`tx_hash is None`).
        - We keep expired invoices in the monitoring index to detect late payments.

        Returns:
            List of newly expired Invoices
        """
        r = await self._get_redis()
        from datetime import UTC, datetime

        now = datetime.now(UTC).timestamp()

        # Invoices that are past their UI expiry
        invoice_ids = await r.zrangebyscore(TwoPhaseRedisKeys.PENDING_INVOICES, "-inf", now)

        expired: list[Invoice] = []
        for iid in invoice_ids:
            invoice = await self.get_invoice(iid)
            if invoice is None:
                await r.zrem(TwoPhaseRedisKeys.PENDING_INVOICES, iid)
                continue

            # Only expire once, and only if no payment has been detected.
            if invoice.status == InvoiceStatus.AWAITING_PAYMENT and invoice.tx_hash is None and invoice.is_expired():
                invoice.status = InvoiceStatus.EXPIRED
                await self._save_invoice(invoice)
                expired.append(invoice)
                logger.info("invoice_expired", invoice_id=iid, offer_id=invoice.cheque_offer_id)

        return expired

    # ======================================================================
    # Helper Methods
    # ======================================================================

    async def _save_offer(self, offer: ChequeOffer) -> None:
        """Save ChequeOffer to Redis with TTL."""
        key = TwoPhaseRedisKeys.offer(offer.offer_id)

        # Calculate TTL based on status
        if offer.is_final():
            ttl = 7 * 86400  # 7 days for completed/cancelled
        else:
            ttl = OFFER_TTL_SECONDS

        await self._hset_dict(key, offer.to_dict(), ttl=ttl)

    async def _save_invoice(self, invoice: Invoice) -> None:
        """Save Invoice to Redis with TTL."""
        key = TwoPhaseRedisKeys.invoice(invoice.invoice_id)

        # Calculate TTL based on status
        if invoice.is_final():
            ttl = 7 * 86400  # 7 days for paid/expired/cancelled
        else:
            ttl = INVOICE_TTL_SECONDS

        await self._hset_dict(key, invoice.to_dict(), ttl=ttl)

    async def _add_to_user_offers(self, user_id: str, offer_id: str) -> None:
        """Add offer to user's index."""
        index_key = TwoPhaseRedisKeys.user_offers_index(user_id)
        r = await self._get_redis()
        from datetime import UTC, datetime

        score = datetime.now(UTC).timestamp()
        await r.zadd(index_key, {offer_id: score})

    async def _add_to_pending_offers(self, offer_id: str, expires_at) -> None:
        """Add offer to pending index."""
        r = await self._get_redis()
        score = expires_at.timestamp()
        await r.zadd(TwoPhaseRedisKeys.PENDING_OFFERS, {offer_id: score})

    async def _remove_from_pending_offers(self, offer_id: str) -> None:
        """Remove offer from pending index."""
        r = await self._get_redis()
        await r.zrem(TwoPhaseRedisKeys.PENDING_OFFERS, offer_id)

    async def _add_to_pending_invoices(self, invoice_id: str, expires_at) -> None:
        """Add invoice to pending index."""
        r = await self._get_redis()
        score = expires_at.timestamp()
        await r.zadd(TwoPhaseRedisKeys.PENDING_INVOICES, {invoice_id: score})

    async def _remove_from_pending_invoices(self, invoice_id: str) -> None:
        """Remove invoice from pending index."""
        r = await self._get_redis()
        await r.zrem(TwoPhaseRedisKeys.PENDING_INVOICES, invoice_id)

    async def _hget_dict(self, key: str) -> dict[str, str] | None:
        """Get dictionary from Redis hash."""
        r = await self._get_redis()
        data = await r.hgetall(key)
        if not data:
            return None
        return dict(data)

    async def _hset_dict(self, key: str, data: dict, ttl: int | None = None) -> None:
        """Store dictionary as Redis hash."""
        r = await self._get_redis()
        clean_data = {k: str(v) if v is not None else "" for k, v in data.items()}
        await r.hset(key, mapping=clean_data)
        if ttl is not None and ttl > 0:
            await r.expire(key, ttl)

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis
