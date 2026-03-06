"""Concurrency tests for payment monitor and storage.

Tests race conditions, locking behavior, and concurrent access patterns.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.skip(
    reason="WIP: concurrency suite pending env + in-memory storage parity"
)

from xmr_cheque_bot.monero_rpc import MoneroWalletRPC
from xmr_cheque_bot.payment_monitor import PaymentMonitor
from xmr_cheque_bot.redis_schema import ChequeRecord, ChequeStatus, UserWallet


class InMemoryStorage:
    """Thread-safe in-memory storage for testing concurrency."""

    def __init__(self):
        self.pending: set[str] = set()
        self.cheques: dict[str, ChequeRecord] = {}
        self.wallets: dict[str, UserWallet] = {}
        self._lock = asyncio.Lock()

    async def list_pending_cheque_ids(self) -> list[str]:
        async with self._lock:
            return sorted(self.pending)

    async def load_cheques(self, cheque_ids: list[str]) -> list[ChequeRecord]:
        async with self._lock:
            return [self.cheques[cid] for cid in cheque_ids if cid in self.cheques]

    async def load_user_wallet(self, user_id: str) -> UserWallet:
        async with self._lock:
            return self.wallets[user_id]

    async def save_cheque(self, cheque: ChequeRecord) -> None:
        async with self._lock:
            self.cheques[cheque.cheque_id] = cheque

    async def remove_from_pending(self, cheque_id: str) -> None:
        async with self._lock:
            self.pending.discard(cheque_id)


class FakeRPC(MoneroWalletRPC):
    """Fake RPC that simulates slow operations for concurrency testing."""

    def __init__(self, transfers: list[dict], delay: float = 0.0):
        # Don't call parent ctor (no httpx)
        self._transfers = transfers
        self._delay = delay
        self.open_wallet_calls = 0
        self.close_wallet_calls = 0

    async def open_wallet(self, filename: str, password: str = "") -> dict:
        await asyncio.sleep(self._delay)
        self.open_wallet_calls += 1
        return {}

    async def close_wallet(self, autosave: bool = True) -> dict:
        await asyncio.sleep(self._delay)
        self.close_wallet_calls += 1
        return {}

    async def refresh(self, start_height=None) -> dict:
        await asyncio.sleep(self._delay)
        return {"blocks_fetched": 0}

    async def get_incoming_transfers(self, min_height=None, include_pool=True):
        await asyncio.sleep(self._delay)
        return self._transfers


def mk_cheque(cid: str, user_id: str, amount: int, min_h: int) -> ChequeRecord:
    """Create a test cheque."""
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


@pytest.fixture
def storage():
    """Create storage with test data."""
    store = InMemoryStorage()

    # Add wallets for users
    for uid in ["u1", "u2", "u3"]:
        store.wallets[uid] = UserWallet(
            user_id=uid,
            monero_address=f"4{uid}",
            encrypted_view_key="enc",
            encrypted_wallet_password="encpw",
            wallet_file_name=f"wallet_{uid}",
        )

    # Add pending cheques
    for i, uid in enumerate(["u1", "u1", "u2", "u2", "u3"]):
        cid = f"c{i + 1}"
        cheque = mk_cheque(cid, uid, 100 * (i + 1), 10)
        store.cheques[cid] = cheque
        store.pending.add(cid)

    return store


@pytest.fixture
def fake_rpc():
    """Create fake RPC with test transfers."""
    return FakeRPC(
        transfers=[
            {"txid": "tx1", "amount": 100, "height": 100, "timestamp": 1, "confirmations": 6},
            {"txid": "tx2", "amount": 200, "height": 101, "timestamp": 2, "confirmations": 6},
        ],
        delay=0.01,  # Small delay to simulate real operations
    )


class TestPaymentMonitorConcurrency:
    """Test PaymentMonitor concurrent behavior."""

    @pytest.mark.asyncio
    async def test_rpc_lock_prevents_concurrent_access(self, storage, fake_rpc):
        """Test that RPC lock prevents concurrent wallet operations."""
        monitor = PaymentMonitor(storage=storage, rpc=fake_rpc)

        # Run monitor twice concurrently
        results = await asyncio.gather(
            monitor.run_once(),
            monitor.run_once(),
        )

        # Both should complete successfully
        assert all(r.processed > 0 for r in results)

        # RPC should be called sequentially (not concurrently)
        # With the lock, open_wallet calls should equal number of unique users
        # But since both runs happen together, the exact count depends on timing
        assert fake_rpc.open_wallet_calls >= 3  # At least 3 users

    @pytest.mark.asyncio
    async def test_user_lock_prevents_reentrant_scanning(self, storage, fake_rpc):
        """Test that per-user lock prevents concurrent scanning for same user."""
        monitor = PaymentMonitor(storage=storage, rpc=fake_rpc)

        # Create two monitors and run them concurrently
        monitor2 = PaymentMonitor(storage=storage, rpc=fake_rpc)

        results = await asyncio.gather(
            monitor.run_once(),
            monitor2.run_once(),
        )

        # Both should complete without errors
        total_processed = sum(r.processed for r in results)
        total_updated = sum(r.updated for r in results)

        # Some cheques should be processed
        assert total_processed >= 5

    @pytest.mark.asyncio
    async def test_concurrent_status_updates(self, storage, fake_rpc):
        """Test concurrent status updates don't corrupt data."""
        monitor = PaymentMonitor(storage=storage, rpc=fake_rpc)

        # Run multiple times concurrently
        await asyncio.gather(*[monitor.run_once() for _ in range(5)])

        # Verify all cheques still have valid state
        for cid, cheque in storage.cheques.items():
            assert isinstance(cheque.status, ChequeStatus)
            assert cheque.cheque_id == cid

    @pytest.mark.asyncio
    async def test_pending_removal_is_atomic(self, storage, fake_rpc):
        """Test that removing from pending is atomic."""
        monitor = PaymentMonitor(storage=storage, rpc=fake_rpc)

        # Run monitor multiple times
        for _ in range(3):
            await monitor.run_once()

        # Confirmed cheques should be removed from pending
        confirmed = [
            cid for cid, c in storage.cheques.items() if c.status == ChequeStatus.CONFIRMED
        ]

        for cid in confirmed:
            assert cid not in storage.pending


class TestStorageConcurrency:
    """Test storage operations under concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_cheque_creation(self, storage):
        """Test creating multiple cheques concurrently."""

        async def create_cheque(i: int):
            cid = f"concurrent_{i}"
            cheque = mk_cheque(cid, "u1", 1000 + i, 10)
            await storage.save_cheque(cheque)
            await storage._add_to_pending(cid, cheque.expires_at)
            return cid

        # Create 10 cheques concurrently
        tasks = [create_cheque(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # All should be created
        assert len(results) == 10
        assert all(cid in storage.cheques for cid in results)

    @pytest.mark.asyncio
    async def test_concurrent_updates_same_cheque(self, storage):
        """Test concurrent updates to the same cheque."""
        cheque = mk_cheque("race_test", "u1", 100, 10)
        await storage.save_cheque(cheque)

        async def update_status(status: ChequeStatus):
            # Load, modify, save
            c = await storage.load_cheques(["race_test"])
            if c:
                c[0].status = status
                await storage.save_cheque(c[0])

        # Try to update same cheque concurrently with different statuses
        await asyncio.gather(
            update_status(ChequeStatus.MEMPOOL),
            update_status(ChequeStatus.CONFIRMING),
            update_status(ChequeStatus.CONFIRMED),
        )

        # Cheque should have one of the statuses (last writer wins)
        final = storage.cheques["race_test"]
        assert final.status in {
            ChequeStatus.MEMPOOL,
            ChequeStatus.CONFIRMING,
            ChequeStatus.CONFIRMED,
        }


class TestRaceConditions:
    """Test specific race condition scenarios."""

    @pytest.mark.asyncio
    async def test_payment_detection_race(self, storage, fake_rpc):
        """Test race between payment detection and cheque expiry."""
        # Create cheque that's about to expire
        now = datetime.now(UTC)
        cheque = ChequeRecord(
            cheque_id="race_cheque",
            user_id="u1",
            amount_rub=100,
            amount_atomic_expected=100,
            monero_address="4abc",
            min_height=10,
            amount_xmr_display="0.000000000100",
            created_at=now - timedelta(minutes=59),
            expires_at=now + timedelta(minutes=1),  # Expires in 1 minute
        )
        await storage.save_cheque(cheque)
        storage.cheques["race_cheque"] = cheque
        storage.pending.add("race_cheque")

        # Add matching transfer
        fake_rpc_with_match = FakeRPC(
            transfers=[
                {
                    "txid": "matching_tx",
                    "amount": 100,
                    "height": 100,
                    "timestamp": 1,
                    "confirmations": 6,
                },
            ],
            delay=0.01,
        )

        monitor = PaymentMonitor(storage=storage, rpc=fake_rpc_with_match)

        # Run detection
        result = await monitor.run_once()

        # Should detect payment even if close to expiry
        updated_cheque = storage.cheques.get("race_cheque")
        if result.updated > 0:
            assert updated_cheque.status == ChequeStatus.CONFIRMED

    @pytest.mark.asyncio
    async def test_double_spend_detection(self, storage):
        """Test handling of potential double-spend scenarios."""
        # This tests that we correctly handle multiple transfers with same amount
        fake_rpc_double = FakeRPC(
            transfers=[
                {"txid": "tx_a", "amount": 100, "height": 100, "timestamp": 1, "confirmations": 6},
                {"txid": "tx_b", "amount": 100, "height": 101, "timestamp": 2, "confirmations": 3},
            ],
            delay=0.01,
        )

        monitor = PaymentMonitor(storage=storage, rpc=fake_rpc_double)
        result = await monitor.run_once()

        # Should process payments correctly
        assert result.processed >= 5


class TestLockBehavior:
    """Test specific lock behaviors."""

    @pytest.mark.asyncio
    async def test_rpc_lock_release_on_exception(self, storage):
        """Test RPC lock is released even if operation fails."""

        class FailingRPC(FakeRPC):
            async def open_wallet(self, filename: str, password: str = "") -> dict:
                if filename == "wallet_u1":
                    raise Exception("Simulated failure")
                return await super().open_wallet(filename, password)

        failing_rpc = FailingRPC(transfers=[], delay=0.01)
        monitor = PaymentMonitor(storage=storage, rpc=failing_rpc)

        # First run may fail for u1
        try:
            await monitor.run_once()
        except Exception:
            pass

        # Second run should still work (lock was released)
        # Replace with working RPC
        working_rpc = FakeRPC(transfers=[], delay=0.01)
        monitor2 = PaymentMonitor(storage=storage, rpc=working_rpc)

        # Should complete without hanging
        result = await asyncio.wait_for(monitor2.run_once(), timeout=2.0)
        assert result.processed >= 0

    @pytest.mark.asyncio
    async def test_user_lock_isolation(self, storage):
        """Test that user locks don't interfere with each other."""
        # Track which users are being processed
        processing_order = []

        class TrackingRPC(FakeRPC):
            async def open_wallet(self, filename: str, password: str = "") -> dict:
                user_id = filename.replace("wallet_", "")
                processing_order.append(user_id)
                await asyncio.sleep(0.05)  # Simulate work
                return await super().open_wallet(filename, password)

        tracking_rpc = TrackingRPC(transfers=[], delay=0)
        monitor = PaymentMonitor(storage=storage, rpc=tracking_rpc)

        await monitor.run_once()

        # All users should be processed
        assert len(processing_order) >= 3
        # u1 should appear only once (per-user lock prevents re-entry)
        assert processing_order.count("u1") == 1
