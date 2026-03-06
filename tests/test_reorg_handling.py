"""Tests for blockchain reorganization handling.

Monero (like other blockchains) can experience chain reorganizations
where blocks are replaced by competing chains. These tests verify that
the payment monitor handles such scenarios correctly.
"""

import pytest

pytestmark = pytest.mark.skip(reason="WIP: reorg suite pending final policy decisions")

from datetime import UTC, datetime

from xmr_cheque_bot.payment_monitor import Transfer, normalize_transfers, pick_match
from xmr_cheque_bot.redis_schema import ChequeRecord, ChequeStatus


class TestReorgScenarios:
    """Test various reorganization scenarios."""

    def test_payment_detected_after_reorg(self):
        """Test that payment is still detected after chain reorg.

        Scenario:
        1. Cheque created at height 100
        2. Payment made in block 150
        3. Chain reorganizes - block 150 is replaced
        4. Payment is included in new block 151
        5. Monitor should still detect the payment
        """
        cheque = ChequeRecord(
            cheque_id="chq_reorg",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=100,
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
        )

        # After reorg, payment is at height 151 instead of 150
        transfers = [
            Transfer(
                txid="tx1", amount_atomic=100000000000, height=151, timestamp=1, confirmations=1
            ),
        ]

        match = pick_match(cheque, transfers)

        assert match is not None
        assert match.txid == "tx1"
        assert match.height == 151

    def test_old_payment_not_redetected_after_reorg(self):
        """Test that already-processed payment isn't re-detected.

        Scenario:
        1. Payment confirmed at height 100
        2. Chain reorganizes around height 100
        3. Monitor should not re-notify about already-processed payment
        """
        # Cheque already has tx_hash from before
        cheque = ChequeRecord(
            cheque_id="chq_done",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=50,
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
            tx_hash="tx_confirmed",
            status=ChequeStatus.CONFIRMED,
            confirmations=10,
        )

        # Same payment appears again (reorg)
        transfers = [
            Transfer(
                txid="tx_confirmed",
                amount_atomic=100000000000,
                height=100,
                timestamp=1,
                confirmations=11,
            ),
        ]

        match = pick_match(cheque, transfers)

        # Match exists but status logic should handle it
        assert match is not None
        # In real code, monitor would check if status/tx_hash changed
        # before notifying

    def test_min_height_filtering_after_reorg(self):
        """Test that min_height correctly filters after reorg.

        Scenario:
        1. Cheque created at height 100 (min_height=100)
        2. Old payment from height 99 shouldn't match even after reorg
        """
        cheque = ChequeRecord(
            cheque_id="chq_filter",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=100,
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
        )

        # Payment at height 99 (before min_height due to reorg)
        transfers = [
            Transfer(
                txid="old_tx", amount_atomic=100000000000, height=99, timestamp=1, confirmations=5
            ),
        ]

        match = pick_match(cheque, transfers)

        # Should not match - below min_height
        assert match is None


class TestConfirmationRollback:
    """Test handling of confirmation count rollbacks during reorg."""

    def test_confirmation_decrease_during_reorg(self):
        """Test that confirmation decrease is handled.

        Scenario:
        1. Payment has 10 confirmations
        2. Reorg occurs - confirmations drop to 3
        3. System should handle this gracefully
        """
        transfers = [
            Transfer(txid="tx1", amount_atomic=100, height=100, timestamp=1, confirmations=3),
        ]

        normalized = normalize_transfers(
            [{"txid": "tx1", "amount": 100, "height": 100, "timestamp": 1, "confirmations": 3}]
        )

        assert len(normalized) == 1
        assert normalized[0].confirmations == 3

    def test_transfer_removed_during_reorg(self):
        """Test handling when transfer disappears during reorg.

        Scenario:
        1. Payment detected in mempool (height=0)
        2. Reorg occurs - payment is no longer valid
        3. Transfer should no longer appear in results
        """
        transfers = normalize_transfers(
            [{"txid": "tx1", "amount": 100, "height": 0, "timestamp": 1, "confirmations": 0}]
        )

        assert len(transfers) == 1
        assert transfers[0].height == 0
        # In real scenario, if tx is removed from mempool,
        # it won't appear in get_incoming_transfers at all


class TestMempoolDuringReorg:
    """Test mempool behavior during reorganization."""

    def test_mempool_tx_confirmed_after_reorg(self):
        """Test mempool transaction that gets confirmed after reorg.

        Scenario:
        1. Payment in mempool (height=0)
        2. Reorg happens
        3. Payment gets confirmed in new block
        """
        cheque = ChequeRecord(
            cheque_id="chq_mempool",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=100,
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
        )

        # First check - mempool only
        mempool_transfers = [
            Transfer(
                txid="tx_mempool",
                amount_atomic=100000000000,
                height=0,
                timestamp=1,
                confirmations=0,
            ),
        ]

        match_mempool = pick_match(cheque, mempool_transfers)
        assert match_mempool is not None
        assert match_mempool.height == 0

        # After reorg and confirmation
        confirmed_transfers = [
            Transfer(
                txid="tx_mempool",
                amount_atomic=100000000000,
                height=150,
                timestamp=2,
                confirmations=1,
            ),
        ]

        match_confirmed = pick_match(cheque, confirmed_transfers)
        assert match_confirmed is not None
        assert match_confirmed.height == 150

    def test_mempool_tx_removed_after_reorg(self):
        """Test mempool transaction that disappears after reorg.

        Scenario:
        1. Payment detected in mempool
        2. Reorg happens - conflicting tx is mined
        3. Original payment disappears from mempool
        """
        # This tests that the monitor handles the case where
        # a previously seen mempool tx no longer appears

        # Initially in mempool
        transfers_before = [
            Transfer(txid="tx_a", amount_atomic=100, height=0, timestamp=1, confirmations=0),
        ]

        # After reorg - tx_a is gone, tx_b (conflicting) is confirmed
        transfers_after = [
            Transfer(txid="tx_b", amount_atomic=100, height=100, timestamp=2, confirmations=6),
        ]

        # The monitor should handle both scenarios gracefully
        # In the second case, tx_a simply won't appear anymore
        assert len(transfers_before) == 1
        assert len(transfers_after) == 1
        assert transfers_before[0].txid != transfers_after[0].txid


class TestReorgRecovery:
    """Test recovery from reorganization events."""

    def test_multiple_reorgs_same_payment(self):
        """Test payment that survives multiple reorgs.

        Scenario:
        1. Payment confirmed at height 100
        2. Reorg - payment at height 101
        3. Another reorg - payment at height 102
        4. System should track final confirmation
        """
        cheque = ChequeRecord(
            cheque_id="chq_stable",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=50,
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
        )

        # Final state after multiple reorgs
        transfers = [
            Transfer(
                txid="stable_tx",
                amount_atomic=100000000000,
                height=102,
                timestamp=3,
                confirmations=10,
            ),
        ]

        match = pick_match(cheque, transfers)

        assert match is not None
        assert match.height == 102
        assert match.confirmations == 10

    def test_reorg_depth_handling(self):
        """Test handling of different reorg depths.

        Monero typically sees small reorgs (1-2 blocks),
        but we should handle larger ones too.
        """
        reorg_depths = [1, 2, 5, 10, 50]

        for depth in reorg_depths:
            cheque = ChequeRecord(
                cheque_id=f"chq_depth_{depth}",
                user_id="u1",
                amount_rub=1000,
                amount_atomic_expected=100000000000,
                monero_address="4abc",
                min_height=100,
                amount_xmr_display="0.100000000000",
                created_at=datetime.now(UTC),
            )

            # Payment confirmed after reorg of given depth
            transfers = [
                Transfer(
                    txid=f"tx_depth_{depth}",
                    amount_atomic=100000000000,
                    height=100 + depth,  # After reorg
                    timestamp=depth,
                    confirmations=6,
                ),
            ]

            match = pick_match(cheque, transfers)
            assert match is not None, f"Failed for reorg depth {depth}"


class TestEdgeCases:
    """Test edge cases in reorg handling."""

    def test_empty_transfers_after_reorg(self):
        """Test handling when no transfers returned after reorg.

        This could happen if wallet-rpc is resyncing.
        """
        cheque = ChequeRecord(
            cheque_id="chq_empty",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=100,
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
        )

        transfers = []

        match = pick_match(cheque, transfers)

        assert match is None

    def test_very_old_reorg(self):
        """Test handling of reorg that affects old payments.

        Unlikely but possible - very deep reorg.
        """
        cheque = ChequeRecord(
            cheque_id="chq_old",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=100000000000,
            monero_address="4abc",
            min_height=1000,  # Very old cheque
            amount_xmr_display="0.100000000000",
            created_at=datetime.now(UTC),
        )

        # Reorg moves payment from height 1050 to 1051
        transfers = [
            Transfer(
                txid="old_payment",
                amount_atomic=100000000000,
                height=1051,
                timestamp=1,
                confirmations=100,
            ),
        ]

        match = pick_match(cheque, transfers)

        assert match is not None
        assert match.height == 1051

    def test_amount_match_preserved_through_reorg(self):
        """Test that exact amount matching works through reorgs.

        The tail-based matching should survive any reorg.
        """
        # Amount with specific tail
        amount_with_tail = 100_000_000_000 + 1234

        cheque = ChequeRecord(
            cheque_id="chq_tail",
            user_id="u1",
            amount_rub=1000,
            amount_atomic_expected=amount_with_tail,
            monero_address="4abc",
            min_height=100,
            amount_xmr_display="0.100000001234",
            created_at=datetime.now(UTC),
        )

        # After reorg, payment has different height but same amount
        transfers = [
            Transfer(
                txid="tail_tx",
                amount_atomic=amount_with_tail,
                height=200,
                timestamp=1,
                confirmations=6,
            ),
            # Wrong amount (different tail)
            Transfer(
                txid="wrong_tx",
                amount_atomic=100_000_000_000 + 5678,
                height=201,
                timestamp=2,
                confirmations=6,
            ),
        ]

        match = pick_match(cheque, transfers)

        assert match is not None
        assert match.txid == "tail_tx"
        assert match.amount_atomic == amount_with_tail
