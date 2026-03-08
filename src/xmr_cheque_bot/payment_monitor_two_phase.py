"""Updated payment monitor for two-phase cheque system.

Watches for payments to Invoice.amount_atomic_expected instead of legacy ChequeRecord.
Matches by: address + exact atomic amount.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog

from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.monero_rpc import MoneroRPCError, MoneroWalletRPC
from xmr_cheque_bot.payment_monitor import is_safe_wallet_filename
from xmr_cheque_bot.redis_schema_two_phase import (
    Invoice,
    InvoiceStatus,
    TwoPhaseRedisKeys,
)
from xmr_cheque_bot.storage_two_phase import TwoPhaseStorage

logger = structlog.get_logger()


@dataclass(frozen=True)
class Transfer:
    """Normalized incoming transfer."""

    txid: str
    amount_atomic: int
    height: int  # 0 if mempool
    timestamp: int
    confirmations: int


class Notifier(Protocol):
    async def notify(
        self, user_id: str, message_key: str, payload: dict
    ) -> None:  # pragma: no cover
        ...


class NoOpNotifier:
    async def notify(self, user_id: str, message_key: str, payload: dict) -> None:
        return


@dataclass
class MonitorResult:
    processed: int
    updated: int
    expired: int


def normalize_transfers(raw: list[dict]) -> list[Transfer]:
    """Normalize raw RPC transfers to Transfer objects."""
    out: list[Transfer] = []
    for t in raw:
        out.append(
            Transfer(
                txid=str(t.get("txid") or t.get("tx_hash") or ""),
                amount_atomic=int(t.get("amount", 0)),
                height=int(t.get("height", 0)),
                timestamp=int(t.get("timestamp", 0)),
                confirmations=int(t.get("confirmations", 0)),
            )
        )
    return out


def pick_match(invoice: Invoice, transfers: list[Transfer]) -> Transfer | None:
    """Pick a transfer that pays this invoice.

    Rules:
    - Exact atomic amount match
    - Height >= min_height for confirmed transfers; mempool height=0 allowed
    - Choose earliest (by height then timestamp) if multiple
    """
    candidates: list[Transfer] = []
    for t in transfers:
        if t.amount_atomic != invoice.amount_atomic_expected:
            continue
        # Height guard: confirmed transfers must be >= min_height; mempool height=0 allowed.
        if t.height != 0 and t.height < int(getattr(invoice, "min_height", 0) or 0):
            continue
        candidates.append(t)

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x.height if x.height != 0 else 10**18, x.timestamp))
    return candidates[0]


def status_from_transfer(t: Transfer, confirmations_final: int) -> InvoiceStatus:
    """Determine invoice status from transfer state."""
    if t.height == 0 or t.confirmations == 0:
        return InvoiceStatus.AWAITING_PAYMENT  # Will be detected as paid in next scan
    # For now, any confirmed transfer = PAID
    return InvoiceStatus.PAID


class InvoicePaymentMonitor:
    """Payment monitor for two-phase Invoice system.

    Monitors pending invoices and detects payments by exact atomic amount.
    """

    def __init__(
        self,
        storage: TwoPhaseStorage,
        rpc: MoneroWalletRPC,
        notifier: Notifier | None = None,
    ) -> None:
        self.storage = storage
        self.rpc = rpc
        self.notifier = notifier or NoOpNotifier()

        # Global lock because monero-wallet-rpc has single open wallet
        self._rpc_lock = asyncio.Lock()
        # Per-user lock to avoid re-entrant scanning
        self._user_locks: dict[str, asyncio.Lock] = {}

    def _lock_for_user(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def run_forever(self) -> None:
        """Run monitor loop indefinitely."""
        settings = get_settings()
        interval = int(getattr(settings, "monitor_interval_sec", 30))

        consecutive_errors = 0
        while True:
            try:
                result = await self.run_once()
                consecutive_errors = 0
                logger.debug(
                    "monitor_cycle_complete",
                    processed=result.processed,
                    updated=result.updated,
                    expired=result.expired,
                )
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                consecutive_errors += 1
                backoff = min(60, interval * (2 ** min(consecutive_errors, 4)))
                logger.error(
                    "monitor_loop_error",
                    error=str(e),
                    consecutive_errors=consecutive_errors,
                    backoff_sec=backoff,
                )
                await asyncio.sleep(backoff)

    async def run_once(self) -> MonitorResult:
        """Single monitoring cycle.

        1. Expire old invoices
        2. Check pending invoices for payments
        """
        settings = get_settings()
        confirmations_final = int(settings.confirmations_final)

        # Step 1: Mark expired invoices
        expired_invoices = await self.storage.expire_old_invoices()

        # Step 2: Get pending invoices
        pending_invoices = await self.storage.list_pending_invoices()
        if not pending_invoices:
            return MonitorResult(processed=0, updated=0, expired=len(expired_invoices))

        # Group invoices by seller (user_id)
        by_user: dict[str, list[Invoice]] = {}
        for inv in pending_invoices:
            # Get offer to find seller
            offer = await self.storage.get_offer(inv.cheque_offer_id)
            if offer:
                by_user.setdefault(offer.seller_user_id, []).append(inv)

        processed = 0
        updated = 0

        for user_id, user_invoices in by_user.items():
            async with self._lock_for_user(user_id):
                wallet = await self._get_user_wallet(user_id)
                if wallet is None:
                    continue

                # Scan from min_height among user's invoices (anti-replay guard)
                min_h = min((int(inv.min_height or 0) for inv in user_invoices), default=0)

                # Get wallet password if available
                wallet_password = ""
                if hasattr(self.storage, "decrypt_wallet_password"):
                    try:
                        wallet_password = await self.storage.decrypt_wallet_password(wallet)
                    except Exception:
                        pass

                try:
                    async with self._rpc_lock:
                        if not wallet.wallet_file_name:
                            continue
                        if not is_safe_wallet_filename(wallet.wallet_file_name):
                            logger.warning("wallet_file_name_invalid", user_id=user_id)
                            continue

                        await self.rpc.open_wallet(
                            filename=wallet.wallet_file_name,
                            password=wallet_password,
                        )
                        try:
                            await self.rpc.refresh(start_height=min_h)
                            raw = await self.rpc.get_incoming_transfers(
                                min_height=min_h,
                                include_pool=True,
                            )
                        finally:
                            await self.rpc.close_wallet(autosave=True)
                except MoneroRPCError as e:
                    logger.error(
                        "monitor_rpc_error",
                        user_id=user_id,
                        method=getattr(e, "method", None),
                        error=str(e),
                    )
                    continue
                except Exception as e:
                    logger.error("monitor_rpc_failed", user_id=user_id, error=str(e))
                    continue

                transfers = normalize_transfers(raw)

                for invoice in user_invoices:
                    processed += 1
                    match = pick_match(invoice, transfers)
                    if not match:
                        continue

                    # Payment detected (mempool/confirming/final)
                    prev_tx = invoice.tx_hash
                    prev_conf = invoice.confirmations

                    # Update progress first (keeps invoice in monitoring index)
                    await self.storage.update_invoice_payment_progress(
                        invoice_id=invoice.invoice_id,
                        tx_hash=match.txid,
                        tx_height=match.height if match.height > 0 else None,
                        confirmations=match.confirmations,
                    )
                    updated += 1

                    # First time we see this payment → notify
                    if prev_tx is None:
                        await self._notify_payment_detected(user_id, invoice, match)

                    # Finalize only when fully confirmed
                    if match.height != 0 and match.confirmations >= confirmations_final:
                        await self.storage.mark_invoice_paid(
                            invoice_id=invoice.invoice_id,
                            tx_hash=match.txid,
                            tx_height=match.height,
                            confirmations=match.confirmations,
                        )
                        updated += 1
                        await self._notify_confirmations(user_id, invoice, match, confirmations_final)
                    else:
                        # Notify on milestones when confirmations change
                        if prev_conf != match.confirmations:
                            await self._notify_confirmations(user_id, invoice, match, confirmations_final)

        return MonitorResult(
            processed=processed,
            updated=updated,
            expired=len(expired_invoices),
        )

    async def _get_user_wallet(self, user_id: str):
        """Get user wallet, with fallback to legacy storage."""
        try:
            return await self.storage.load_user_wallet(user_id)
        except Exception:
            return None

    async def _notify_payment_detected(
        self,
        user_id: str,
        invoice: Invoice,
        transfer: Transfer,
    ) -> None:
        """Notify seller that payment was detected."""
        offer = await self.storage.get_offer(invoice.cheque_offer_id)
        if offer is None:
            return

        await self.notifier.notify(
            user_id,
            "payment.mempool" if transfer.height == 0 else "payment.detected",
            {
                "offer_id": invoice.cheque_offer_id,
                "invoice_id": invoice.invoice_id,
                "amount_rub": offer.amount_rub,
                "amount_xmr": invoice.amount_xmr,
                "tx_hash": transfer.txid[:16] + "...",
            },
        )

    async def _notify_confirmations(
        self,
        user_id: str,
        invoice: Invoice,
        transfer: Transfer,
        confirmations_final: int,
    ) -> None:
        """Notify seller on confirmation milestones."""
        offer = await self.storage.get_offer(invoice.cheque_offer_id)
        if offer is None:
            return

        # Milestones: 1 confirmation, half, final
        conf = transfer.confirmations

        if conf >= confirmations_final:
            await self.notifier.notify(
                user_id,
                "payment.confirmed",
                {
                    "offer_id": invoice.cheque_offer_id,
                    "invoice_id": invoice.invoice_id,
                    "amount_rub": offer.amount_rub,
                    "amount_xmr": invoice.amount_xmr,
                    "confirmations": conf,
                    "final": confirmations_final,
                },
            )
        elif conf == 1 or conf == confirmations_final // 2:
            await self.notifier.notify(
                user_id,
                "payment.confirming",
                {
                    "offer_id": invoice.cheque_offer_id,
                    "invoice_id": invoice.invoice_id,
                    "confirmations": conf,
                    "final": confirmations_final,
                },
            )
