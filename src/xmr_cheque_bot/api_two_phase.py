"""API endpoints for two-phase cheque system.

Implements REST API for:
- ChequeOffer management (create, get, cancel)
- Invoice generation and refresh
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog

from xmr_cheque_bot.storage_two_phase import TwoPhaseStorage, TwoPhaseStorageError
from xmr_cheque_bot.redis_schema_two_phase import (
    ChequeOffer,
    Invoice,
    InvoiceStatus,
    OfferStatus,
)
from xmr_cheque_bot.rates import fetch_xmr_rub_rate, RateFetchError
from xmr_cheque_bot.amount import atomic_to_xmr

logger = structlog.get_logger()


# =============================================================================
# Response Models
# =============================================================================


@dataclass
class ChequeOfferResponse:
    """Response for ChequeOffer operations."""

    offer_id: str
    amount_rub: int
    description: str
    recipient_address: str
    status: str
    expires_at: str
    created_at: str
    current_invoice_id: str | None

    @classmethod
    def from_offer(cls, offer: ChequeOffer) -> "ChequeOfferResponse":
        return cls(
            offer_id=offer.offer_id,
            amount_rub=offer.amount_rub,
            description=offer.description,
            recipient_address=offer.recipient_address,
            status=offer.status.value,
            expires_at=offer.expires_at.isoformat(),
            created_at=offer.created_at.isoformat(),
            current_invoice_id=offer.current_invoice_id,
        )


@dataclass
class InvoiceResponse:
    """Response for Invoice operations."""

    invoice_id: str
    cheque_offer_id: str
    amount_xmr: str
    amount_atomic_expected: int
    rate_xmr_rub: str
    status: str
    expires_at: str
    created_at: str
    qr_code_url: str | None = None
    tx_hash: str | None = None
    confirmations: int = 0

    @classmethod
    def from_invoice(cls, invoice: Invoice, qr_code_url: str | None = None) -> "InvoiceResponse":
        return cls(
            invoice_id=invoice.invoice_id,
            cheque_offer_id=invoice.cheque_offer_id,
            amount_xmr=invoice.amount_xmr,
            amount_atomic_expected=invoice.amount_atomic_expected,
            rate_xmr_rub=invoice.rate_xmr_rub,
            status=invoice.status.value,
            expires_at=invoice.expires_at.isoformat(),
            created_at=invoice.created_at.isoformat(),
            qr_code_url=qr_code_url,
            tx_hash=invoice.tx_hash,
            confirmations=invoice.confirmations,
        )


@dataclass
class ChequeOfferWithApproximateResponse:
    """Response for viewing offer with approximate XMR (current rate)."""

    offer_id: str
    amount_rub: int
    description: str
    recipient_address: str
    status: str
    expires_at: str
    created_at: str
    approximate_xmr: str | None  # Current rate approximation (marked with ≈)
    current_rate: str | None  # Current XMR/RUB rate


@dataclass
class ErrorResponse:
    """Error response."""

    error: str
    code: str


# =============================================================================
# ChequeOffer API
# =============================================================================


class ChequeOfferAPI:
    """API for ChequeOffer management."""

    def __init__(self, storage: TwoPhaseStorage) -> None:
        self.storage = storage

    async def create_offer(
        self,
        seller_user_id: str,
        amount_rub: int,
        recipient_address: str,
        description: str = "",
    ) -> ChequeOfferResponse | ErrorResponse:
        """Create a new ChequeOffer.

        Args:
            seller_user_id: Seller's user ID
            amount_rub: Amount in Russian rubles
            recipient_address: Seller's Monero address
            description: Optional description

        Returns:
            ChequeOfferResponse or ErrorResponse
        """
        try:
            # Validate inputs
            if amount_rub < 100:
                return ErrorResponse(
                    error="Amount must be at least 100 RUB",
                    code="INVALID_AMOUNT",
                )

            if amount_rub > 1_000_000:
                return ErrorResponse(
                    error="Amount must not exceed 1,000,000 RUB",
                    code="INVALID_AMOUNT",
                )

            # Create offer
            offer = await self.storage.create_cheque_offer(
                seller_user_id=seller_user_id,
                amount_rub=amount_rub,
                recipient_address=recipient_address,
                description=description,
            )

            logger.info(
                "api_offer_created",
                offer_id=offer.offer_id,
                seller_user_id=seller_user_id,
            )

            return ChequeOfferResponse.from_offer(offer)

        except Exception as e:
            logger.error("api_create_offer_failed", error=str(e))
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")

    async def get_offer(
        self,
        offer_id: str,
        include_approximate: bool = False,
    ) -> ChequeOfferWithApproximateResponse | ErrorResponse:
        """Get ChequeOffer details.

        Args:
            offer_id: Offer ID
            include_approximate: Whether to include approximate XMR (current rate)

        Returns:
            ChequeOfferWithApproximateResponse or ErrorResponse
        """
        try:
            offer = await self.storage.get_offer(offer_id)
            if offer is None:
                return ErrorResponse(error="Offer not found", code="NOT_FOUND")

            approximate_xmr = None
            current_rate = None

            if include_approximate:
                try:
                    rate = await fetch_xmr_rub_rate()
                    current_rate = str(rate)
                    # Calculate approximate XMR
                    from decimal import Decimal
                    approx = Decimal(offer.amount_rub) / rate
                    approximate_xmr = f"{approx:.6f}"
                except RateFetchError:
                    pass  # Silently omit approximate if rate fetch fails

            return ChequeOfferWithApproximateResponse(
                offer_id=offer.offer_id,
                amount_rub=offer.amount_rub,
                description=offer.description,
                recipient_address=offer.recipient_address,
                status=offer.status.value,
                expires_at=offer.expires_at.isoformat(),
                created_at=offer.created_at.isoformat(),
                approximate_xmr=approximate_xmr,
                current_rate=current_rate,
            )

        except Exception as e:
            logger.error("api_get_offer_failed", error=str(e))
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")

    async def cancel_offer(
        self,
        offer_id: str,
        seller_user_id: str,
    ) -> ChequeOfferResponse | ErrorResponse:
        """Cancel a pending offer.

        Args:
            offer_id: Offer ID
            seller_user_id: Seller's user ID (for authorization)

        Returns:
            ChequeOfferResponse or ErrorResponse
        """
        try:
            offer = await self.storage.get_offer(offer_id)
            if offer is None:
                return ErrorResponse(error="Offer not found", code="NOT_FOUND")

            if offer.seller_user_id != seller_user_id:
                return ErrorResponse(error="Not authorized", code="UNAUTHORIZED")

            cancelled = await self.storage.cancel_offer(offer_id)
            if cancelled is None:
                return ErrorResponse(error="Failed to cancel offer", code="CANCEL_FAILED")

            return ChequeOfferResponse.from_offer(cancelled)

        except TwoPhaseStorageError as e:
            return ErrorResponse(error=str(e), code="INVALID_STATE")
        except Exception as e:
            logger.error("api_cancel_offer_failed", error=str(e))
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")


# =============================================================================
# Invoice API
# =============================================================================


class InvoiceAPI:
    """API for Invoice generation and management."""

    def __init__(self, storage: TwoPhaseStorage) -> None:
        self.storage = storage

    async def generate_invoice(
        self,
        offer_id: str,
        payer_user_id: str | None = None,
        min_height: int = 0,
    ) -> InvoiceResponse | ErrorResponse:
        """Generate a new Invoice for an offer (when payer clicks "Pay").

        Args:
            offer_id: Parent ChequeOffer ID
            payer_user_id: Optional payer ID for tracking
            min_height: Minimum block height for tx filtering

        Returns:
            InvoiceResponse or ErrorResponse
        """
        try:
            offer = await self.storage.get_offer(offer_id)
            if offer is None:
                return ErrorResponse(error="Offer not found", code="NOT_FOUND")

            if offer.is_expired():
                return ErrorResponse(error="Offer has expired", code="OFFER_EXPIRED")

            if offer.status != OfferStatus.PENDING:
                return ErrorResponse(
                    error=f"Offer is not available: {offer.status.value}",
                    code="OFFER_NOT_AVAILABLE",
                )

            # Generate invoice with current rate
            invoice = await self.storage.generate_invoice(
                offer_id=offer_id,
                min_height=min_height,
            )

            logger.info(
                "api_invoice_generated",
                invoice_id=invoice.invoice_id,
                offer_id=offer_id,
                payer_user_id=payer_user_id,
            )

            return InvoiceResponse.from_invoice(invoice)

        except TwoPhaseStorageError as e:
            return ErrorResponse(error=str(e), code="GENERATION_FAILED")
        except RateFetchError as e:
            return ErrorResponse(error=f"Failed to fetch rate: {e}", code="RATE_FETCH_FAILED")
        except Exception as e:
            logger.error("api_generate_invoice_failed", error=str(e))
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")

    async def refresh_invoice(
        self,
        invoice_id: str,
        payer_user_id: str | None = None,
        min_height: int = 0,
    ) -> InvoiceResponse | ErrorResponse:
        """Refresh an expired invoice with a new one.

        Args:
            invoice_id: Expired invoice ID
            payer_user_id: Optional payer ID for tracking
            min_height: Minimum block height

        Returns:
            InvoiceResponse or ErrorResponse
        """
        try:
            old_invoice = await self.storage.get_invoice(invoice_id)
            if old_invoice is None:
                return ErrorResponse(error="Invoice not found", code="NOT_FOUND")

            # Verify the invoice is actually expired
            if old_invoice.status != InvoiceStatus.EXPIRED and not old_invoice.is_expired():
                return ErrorResponse(
                    error="Invoice is not expired",
                    code="NOT_EXPIRED",
                )

            # Refresh with current rate
            new_invoice = await self.storage.refresh_invoice(
                invoice_id=invoice_id,
                min_height=min_height,
            )

            logger.info(
                "api_invoice_refreshed",
                new_invoice_id=new_invoice.invoice_id,
                old_invoice_id=invoice_id,
                payer_user_id=payer_user_id,
            )

            return InvoiceResponse.from_invoice(new_invoice)

        except TwoPhaseStorageError as e:
            return ErrorResponse(error=str(e), code="REFRESH_FAILED")
        except RateFetchError as e:
            return ErrorResponse(error=f"Failed to fetch rate: {e}", code="RATE_FETCH_FAILED")
        except Exception as e:
            logger.error("api_refresh_invoice_failed", error=str(e))
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")

    async def get_invoice(
        self,
        invoice_id: str,
    ) -> InvoiceResponse | ErrorResponse:
        """Get Invoice details.

        Args:
            invoice_id: Invoice ID

        Returns:
            InvoiceResponse or ErrorResponse
        """
        try:
            invoice = await self.storage.get_invoice(invoice_id)
            if invoice is None:
                return ErrorResponse(error="Invoice not found", code="NOT_FOUND")

            return InvoiceResponse.from_invoice(invoice)

        except Exception as e:
            logger.error("api_get_invoice_failed", error=str(e))
            return ErrorResponse(error=str(e), code="INTERNAL_ERROR")
