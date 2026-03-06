"""Payment monitor worker (M3).

Scans pending cheques, queries monero-wallet-rpc via watch-only wallets,
matches incoming transfers by exact atomic amount, and advances cheque status.

No Telegram handlers here — notifications go through a Notifier interface.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import structlog

from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.monero_rpc import MoneroRPCError, MoneroWalletRPC
from xmr_cheque_bot.redis_schema import ChequeRecord, ChequeStatus, UserWallet

logger = structlog.get_logger()

# monero-wallet-rpc uses a wallet-dir configured on the daemon, but it is still
# best to validate user-derived filenames to reduce path traversal/odd behavior.
_WALLET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def is_safe_wallet_filename(name: str) -> bool:
    return (
        bool(_WALLET_NAME_RE.fullmatch(name))
        and ".." not in name
        and "/" not in name
        and "\\" not in name
    )


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


class Storage(Protocol):
    """Abstract storage used by the monitor.

    Implemented later with real Redis; unit tests can use an in-memory storage.
    """

    async def list_pending_cheque_ids(self) -> list[str]:  # pragma: no cover
        ...

    async def load_cheques(self, cheque_ids: list[str]) -> list[ChequeRecord]:  # pragma: no cover
        ...

    async def load_user_wallet(self, user_id: str) -> UserWallet:  # pragma: no cover
        ...

    async def save_cheque(self, cheque: ChequeRecord) -> None:  # pragma: no cover
        ...

    async def remove_from_pending(self, cheque_id: str) -> None:  # pragma: no cover
        ...


@dataclass
class MonitorResult:
    processed: int
    updated: int


def normalize_transfers(raw: list[dict]) -> list[Transfer]:
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


def pick_match(cheque: ChequeRecord, transfers: list[Transfer]) -> Transfer | None:
    """Pick a transfer that pays this cheque.

    Rules:
    - exact atomic amount match
    - height >= min_height for confirmed transfers; mempool height=0 allowed
    - choose earliest (by height then timestamp) if multiple.
    """

    candidates: list[Transfer] = []
    for t in transfers:
        if t.amount_atomic != cheque.amount_atomic_expected:
            continue
        if t.height != 0 and t.height < cheque.min_height:
            continue
        candidates.append(t)

    if not candidates:
        return None

    candidates.sort(key=lambda x: (x.height if x.height != 0 else 10**18, x.timestamp))
    return candidates[0]


def status_from_transfer(t: Transfer, confirmations_final: int) -> ChequeStatus:
    if t.height == 0 or t.confirmations == 0:
        return ChequeStatus.MEMPOOL
    if t.confirmations >= confirmations_final:
        return ChequeStatus.CONFIRMED
    return ChequeStatus.CONFIRMING


class PaymentMonitor:
    def __init__(
        self,
        storage: Storage,
        rpc: MoneroWalletRPC,
        notifier: Notifier | None = None,
    ) -> None:
        self.storage = storage
        self.rpc = rpc
        self.notifier = notifier or NoOpNotifier()

        # Global lock because monero-wallet-rpc has a single open wallet at a time.
        self._rpc_lock = asyncio.Lock()
        # Per-user lock to avoid re-entrant scanning for same user.
        self._user_locks: dict[str, asyncio.Lock] = {}

    def _lock_for_user(self, user_id: str) -> asyncio.Lock:
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def run_forever(self) -> None:
        settings = get_settings()
        interval = int(getattr(settings, "monitor_interval_sec", 30))

        consecutive_errors = 0
        while True:
            try:
                await self.run_once()
                consecutive_errors = 0
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
        settings = get_settings()
        confirmations_final = int(settings.confirmations_final)

        pending_ids = await self.storage.list_pending_cheque_ids()
        if not pending_ids:
            return MonitorResult(processed=0, updated=0)

        cheques = await self.storage.load_cheques(pending_ids)
        processed = 0
        updated = 0

        # Group by user
        by_user: dict[str, list[ChequeRecord]] = {}
        for c in cheques:
            by_user.setdefault(c.user_id, []).append(c)

        for user_id, user_cheques in by_user.items():
            async with self._lock_for_user(user_id):
                wallet = await self.storage.load_user_wallet(user_id)
                # scan from min height among user's cheques
                min_h = min(c.min_height for c in user_cheques)

                wallet_password = ""
                if hasattr(self.storage, "decrypt_wallet_password"):
                    wallet_password = await self.storage.decrypt_wallet_password(wallet)  # type: ignore[misc]

                try:
                    async with self._rpc_lock:
                        if not wallet.wallet_file_name:
                            # Can't scan without wallet file
                            continue
                        if not is_safe_wallet_filename(wallet.wallet_file_name):
                            logger.warning("wallet_file_name_invalid", user_id=user_id)
                            continue
                        await self.rpc.open_wallet(
                            filename=wallet.wallet_file_name, password=wallet_password
                        )
                        try:
                            await self.rpc.refresh(start_height=min_h)
                            raw = await self.rpc.get_incoming_transfers(
                                min_height=min_h, include_pool=True
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

                for cheque in user_cheques:
                    processed += 1
                    match = pick_match(cheque, transfers)
                    if not match:
                        continue

                    new_status = status_from_transfer(match, confirmations_final)
                    if (
                        new_status == cheque.status
                        and cheque.tx_hash == match.txid
                        and cheque.confirmations == match.confirmations
                    ):
                        continue

                    cheque.tx_hash = match.txid
                    cheque.tx_height = match.height if match.height != 0 else None
                    cheque.confirmations = match.confirmations
                    cheque.status = new_status
                    if new_status == ChequeStatus.CONFIRMED and cheque.paid_at is None:
                        cheque.paid_at = datetime.now(UTC)

                    await self.storage.save_cheque(cheque)
                    updated += 1

                    if new_status in {
                        ChequeStatus.CONFIRMED,
                        ChequeStatus.EXPIRED,
                        ChequeStatus.CANCELLED,
                    }:
                        await self.storage.remove_from_pending(cheque.cheque_id)

                    # Notifications (keys only; bot layer maps them to RU/EN)
                    if new_status == ChequeStatus.MEMPOOL:
                        await self.notifier.notify(
                            user_id, "payment.mempool", {"cheque_id": cheque.cheque_id}
                        )
                    elif new_status == ChequeStatus.CONFIRMING:
                        await self.notifier.notify(
                            user_id,
                            "payment.confirming",
                            {
                                "cheque_id": cheque.cheque_id,
                                "confirmations": cheque.confirmations,
                                "final": confirmations_final,
                            },
                        )
                    elif new_status == ChequeStatus.CONFIRMED:
                        await self.notifier.notify(
                            user_id,
                            "payment.confirmed",
                            {"cheque_id": cheque.cheque_id, "confirmations": cheque.confirmations},
                        )

        return MonitorResult(processed=processed, updated=updated)
