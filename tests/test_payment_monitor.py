from datetime import UTC, datetime, timedelta

import pytest

from xmr_cheque_bot.monero_rpc import MoneroWalletRPC
from xmr_cheque_bot.payment_monitor import (
    PaymentMonitor,
    Transfer,
    pick_match,
    status_from_transfer,
)
from xmr_cheque_bot.redis_schema import ChequeRecord, ChequeStatus, UserWallet


class InMemoryStorage:
    def __init__(self) -> None:
        self.pending: set[str] = set()
        self.cheques: dict[str, ChequeRecord] = {}
        self.wallets: dict[str, UserWallet] = {}

    async def list_pending_cheque_ids(self) -> list[str]:
        return sorted(self.pending)

    async def load_cheques(self, cheque_ids: list[str]) -> list[ChequeRecord]:
        return [self.cheques[cid] for cid in cheque_ids]

    async def load_user_wallet(self, user_id: str) -> UserWallet:
        return self.wallets[user_id]

    async def save_cheque(self, cheque: ChequeRecord) -> None:
        self.cheques[cheque.cheque_id] = cheque

    async def remove_from_pending(self, cheque_id: str) -> None:
        self.pending.discard(cheque_id)


class FakeRPC(MoneroWalletRPC):
    def __init__(self, transfers: list[dict]):
        # Don't call parent ctor (no httpx)
        self._transfers = transfers

    async def open_wallet(self, filename: str, password: str = "") -> dict:
        return {}

    async def close_wallet(self, autosave: bool = True) -> dict:
        return {}

    async def refresh(self, start_height=None) -> dict:
        return {"blocks_fetched": 0}

    async def get_incoming_transfers(self, min_height=None, include_pool=True):
        return self._transfers


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Settings required by get_settings
    from xmr_cheque_bot.encryption import EncryptionManager

    monkeypatch.setenv("BOT_TOKEN", "test")
    monkeypatch.setenv("VIEW_KEY_ENCRYPTION_KEY", EncryptionManager.generate_key())


def mk_cheque(cid: str, user_id: str, amount: int, min_h: int) -> ChequeRecord:
    now = datetime.now(UTC)
    return ChequeRecord(
        cheque_id=cid,
        user_id=user_id,
        amount_rub=100,
        amount_atomic_expected=amount,
        monero_address="4abc",
        min_height=min_h,
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )


def test_pick_match_exact_and_min_height() -> None:
    cheque = mk_cheque("c1", "u1", 123, 10)
    transfers = [
        Transfer(txid="old", amount_atomic=123, height=9, timestamp=1, confirmations=1),
        Transfer(txid="ok", amount_atomic=123, height=10, timestamp=2, confirmations=1),
    ]
    assert pick_match(cheque, transfers).txid == "ok"


def test_status_from_transfer() -> None:
    assert status_from_transfer(Transfer("t", 1, 0, 0, 0), 6) == ChequeStatus.MEMPOOL
    assert status_from_transfer(Transfer("t", 1, 100, 0, 1), 6) == ChequeStatus.CONFIRMING
    assert status_from_transfer(Transfer("t", 1, 100, 0, 6), 6) == ChequeStatus.CONFIRMED


@pytest.mark.asyncio
async def test_monitor_updates_and_removes_pending_on_confirmed() -> None:
    storage = InMemoryStorage()
    storage.wallets["u1"] = UserWallet(
        user_id="u1",
        monero_address="4abc",
        encrypted_view_key="enc",
        encrypted_wallet_password="encpw",
        wallet_file_name="vw_u1",
    )

    c1 = mk_cheque("c1", "u1", 555, 10)
    storage.cheques[c1.cheque_id] = c1
    storage.pending.add(c1.cheque_id)

    rpc = FakeRPC(
        transfers=[
            {"txid": "tx1", "amount": 555, "height": 100, "timestamp": 1, "confirmations": 6},
        ]
    )

    monitor = PaymentMonitor(storage=storage, rpc=rpc)
    res = await monitor.run_once()

    assert res.processed == 1
    assert res.updated == 1
    assert storage.cheques["c1"].status == ChequeStatus.CONFIRMED
    assert "c1" not in storage.pending


@pytest.mark.asyncio
async def test_monitor_sets_mempool() -> None:
    storage = InMemoryStorage()
    storage.wallets["u1"] = UserWallet(
        user_id="u1",
        monero_address="4abc",
        encrypted_view_key="enc",
        encrypted_wallet_password="encpw",
        wallet_file_name="vw_u1",
    )
    c1 = mk_cheque("c1", "u1", 777, 10)
    storage.cheques[c1.cheque_id] = c1
    storage.pending.add(c1.cheque_id)

    rpc = FakeRPC(
        transfers=[
            {"txid": "txm", "amount": 777, "height": 0, "timestamp": 1, "confirmations": 0},
        ]
    )

    monitor = PaymentMonitor(storage=storage, rpc=rpc)
    res = await monitor.run_once()

    assert res.updated == 1
    assert storage.cheques["c1"].status == ChequeStatus.MEMPOOL
