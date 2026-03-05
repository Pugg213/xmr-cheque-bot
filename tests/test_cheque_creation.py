"""Unit tests for cheque creation modules (M2).

Tests:
- Amount computation (atomic math, tail uniqueness)
- URI formatting
- Rate fetching (mocked)
- QR generation
- Cheque limits
"""

import pytest
from decimal import Decimal, InvalidOperation
from unittest.mock import AsyncMock, MagicMock, patch

# Import modules under test
from xmr_cheque_bot.amount import (
    ATOMIC_UNITS_PER_XMR,
    MIN_TAIL,
    MAX_TAIL,
    ComputedAmount,
    _atomic_to_display,
    atomic_to_xmr,
    compute_cheque_amount,
    generate_unique_tail,
    validate_tail,
    xmr_to_atomic,
)
from xmr_cheque_bot.cheque_limits import (
    ChequeLimitError,
    check_cheque_creation_allowed,
    count_active_cheques,
    get_active_statuses,
    is_status_active,
)
from xmr_cheque_bot.redis_schema import ChequeStatus
from xmr_cheque_bot.rates import RateFetchError, RateCache, fetch_xmr_rub_rate
from xmr_cheque_bot.uri_qr import (
    build_monero_uri,
    generate_payment_qr,
    generate_qr_code,
    get_qr_size_for_data,
)


# =============================================================================
# Amount Computation Tests
# =============================================================================

class TestAmountComputation:
    """Tests for amount computation with Decimal precision."""

    @pytest.mark.asyncio
    async def test_basic_computation(self):
        """Test basic amount computation with mocked rate."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("15000.00")  # 1 XMR = 15000 RUB
            
            result = await compute_cheque_amount(1500)  # 1500 RUB = 0.1 XMR
            
            assert result.amount_rub == 1500
            assert result.rate_xmr_rub == Decimal("15000.00")
            assert result.amount_atomic_expected > 0
            assert result.base_atomic > 0
            assert MIN_TAIL <= result.tail <= MAX_TAIL
            assert result.amount_atomic_expected == result.base_atomic + result.tail

    @pytest.mark.asyncio
    async def test_computation_with_specific_tail(self):
        """Test computation with explicit tail value."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("10000.00")
            
            result = await compute_cheque_amount(1000, tail=1234)
            
            assert result.tail == 1234
            assert result.amount_atomic_expected == result.base_atomic + 1234

    @pytest.mark.asyncio
    async def test_amount_xmr_display_format(self):
        """Test display string has exactly 12 decimal places."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("10000.00")
            
            result = await compute_cheque_amount(1000)
            
            # Should have exactly 12 decimal places
            assert "." in result.amount_xmr_display
            decimal_places = len(result.amount_xmr_display.split(".")[1])
            assert decimal_places == 12

    @pytest.mark.asyncio
    async def test_atomic_math_precision(self):
        """Test atomic math avoids float drift."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("12345.67")
            
            result = await compute_cheque_amount(999)
            
            # Verify we're using Decimal, not float
            assert isinstance(result.rate_xmr_rub, Decimal)
            
            # Verify atomic amount is integer
            assert isinstance(result.amount_atomic_expected, int)
            
            # Reconstruct and verify no drift
            reconstructed = atomic_to_xmr(result.amount_atomic_expected)
            reconstructed_atomic = xmr_to_atomic(reconstructed)
            assert reconstructed_atomic == result.amount_atomic_expected

    @pytest.mark.asyncio
    async def test_computation_is_deterministic_with_same_tail(self):
        """Test that same inputs produce same outputs."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("20000.00")
            
            result1 = await compute_cheque_amount(500, tail=100)
            result2 = await compute_cheque_amount(500, tail=100)
            
            assert result1.amount_atomic_expected == result2.amount_atomic_expected
            assert result1.amount_xmr_display == result2.amount_xmr_display
            assert result1.base_atomic == result2.base_atomic

    @pytest.mark.asyncio
    async def test_different_tails_produce_different_amounts(self):
        """Test that different tails create unique expected amounts."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("10000.00")
            
            result1 = await compute_cheque_amount(1000, tail=1)
            result2 = await compute_cheque_amount(1000, tail=9999)
            
            assert result1.amount_atomic_expected != result2.amount_atomic_expected
            assert result1.tail != result2.tail

    @pytest.mark.asyncio
    async def test_invalid_amount_rub(self):
        """Test validation of negative or zero RUB amount."""
        with pytest.raises(ValueError, match="must be positive"):
            await compute_cheque_amount(0)
        
        with pytest.raises(ValueError, match="must be positive"):
            await compute_cheque_amount(-100)

    @pytest.mark.asyncio
    async def test_invalid_tail_range(self):
        """Test validation of out-of-range tail values."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("10000.00")
            
            with pytest.raises(ValueError, match="tail must be between"):
                await compute_cheque_amount(1000, tail=0)
            
            with pytest.raises(ValueError, match="tail must be between"):
                await compute_cheque_amount(1000, tail=10000)
            
            with pytest.raises(ValueError, match="tail must be between"):
                await compute_cheque_amount(1000, tail=-1)

    @pytest.mark.asyncio
    async def test_rate_fetch_error_propagation(self):
        """Test that rate fetch errors are propagated."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.side_effect = RateFetchError("API unavailable")
            
            with pytest.raises(RateFetchError, match="API unavailable"):
                await compute_cheque_amount(1000)


class TestAtomicConversions:
    """Tests for atomic unit conversions."""

    def test_atomic_to_display_zero(self):
        """Test display of zero atomic units."""
        assert _atomic_to_display(0) == "0.000000000000"

    def test_atomic_to_display_one_xmr(self):
        """Test display of 1 XMR in atomic units."""
        one_xmr_atomic = 1_000_000_000_000
        result = _atomic_to_display(one_xmr_atomic)
        assert result == "1.000000000000"

    def test_atomic_to_display_small_amount(self):
        """Test display of small atomic amount."""
        # 1 piconero
        result = _atomic_to_display(1)
        assert result == "0.000000000001"

    def test_atomic_to_display_with_tail(self):
        """Test display preserves tail precision."""
        # Amount with tail 1234
        atomic = 123_456_789_000_000 + 1234
        result = _atomic_to_display(atomic)
        # Should show all 12 decimal places including tail
        assert result.endswith("1234")

    def test_atomic_to_xmr(self):
        """Test conversion to XMR Decimal."""
        atomic = 1_500_000_000_000  # 1.5 XMR
        result = atomic_to_xmr(atomic)
        assert result == Decimal("1.5")

    def test_xmr_to_atomic(self):
        """Test conversion from XMR to atomic."""
        xmr = Decimal("0.123456789012")
        result = xmr_to_atomic(xmr)
        assert result == 123_456_789_012

    def test_round_trip_conversion(self):
        """Test atomic -> XMR -> atomic is lossless."""
        original = 987_654_321_012  # Random atomic amount
        xmr = atomic_to_xmr(original)
        converted = xmr_to_atomic(xmr)
        assert original == converted


class TestTailGeneration:
    """Tests for tail uniqueness and bounds."""

    def test_tail_bounds_constants(self):
        """Test tail bounds are correct."""
        assert MIN_TAIL == 1
        assert MAX_TAIL == 9999

    def test_generate_unique_tail_range(self):
        """Test generated tails are within valid range."""
        for _ in range(100):
            tail = generate_unique_tail()
            assert MIN_TAIL <= tail <= MAX_TAIL

    def test_generate_unique_tail_distribution(self):
        """Test tails are reasonably distributed (basic check)."""
        tails = [generate_unique_tail() for _ in range(1000)]
        unique_tails = set(tails)
        # Should have reasonable variety
        assert len(unique_tails) > 100

    def test_validate_tail_valid(self):
        """Test validation accepts valid tails."""
        assert validate_tail(1) is True
        assert validate_tail(5000) is True
        assert validate_tail(9999) is True

    def test_validate_tail_invalid(self):
        """Test validation rejects invalid tails."""
        assert validate_tail(0) is False
        assert validate_tail(10000) is False
        assert validate_tail(-1) is False


# =============================================================================
# URI Builder Tests
# =============================================================================

class TestMoneroURI:
    """Tests for Monero URI formatting."""

    def test_basic_uri(self):
        """Test basic URI with just address."""
        address = "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uUNzHwJpYdhkRXdDQYFGAXCAw"
        uri = build_monero_uri(address)
        assert uri.startswith("monero:")
        assert address in uri

    def test_uri_with_amount(self):
        """Test URI with amount parameter."""
        uri = build_monero_uri(
            address="44AFFq5k...",
            amount_xmr="0.123456789012"
        )
        assert "tx_amount=0.123456789012" in uri

    def test_uri_with_description(self):
        """Test URI with description (URL encoded)."""
        uri = build_monero_uri(
            address="44AFFq5k...",
            amount_xmr="1.0",
            tx_description="Invoice #123"
        )
        assert "tx_description=" in uri
        assert "Invoice" in uri or "Invoice+%23123" in uri

    def test_uri_with_message(self):
        """Test URI with message."""
        uri = build_monero_uri(
            address="44AFFq5k...",
            tx_message="Payment for services"
        )
        assert "tx_message=Payment+for+services" in uri or "tx_message=Payment%20for%20services" in uri

    def test_uri_all_params(self):
        """Test URI with all parameters."""
        uri = build_monero_uri(
            address="44AFFq5k...",
            amount_xmr="0.5",
            tx_description="Donation",
            tx_message="Keep up the good work!"
        )
        assert uri.startswith("monero:44AFFq5k...")
        assert "tx_amount=0.5" in uri
        assert "tx_description=Donation" in uri
        assert "tx_message=" in uri

    def test_empty_address_raises(self):
        """Test empty address raises ValueError."""
        with pytest.raises(ValueError, match="Address is required"):
            build_monero_uri("")

    def test_invalid_amount_format_raises(self):
        """Test invalid amount format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid amount format"):
            build_monero_uri("44AFFq5k...", amount_xmr="not-a-number")

    def test_uri_no_trailing_question_mark(self):
        """Test URI doesn't have trailing ? when no params."""
        uri = build_monero_uri("44AFFq5k...")
        assert not uri.endswith("?")
        assert "?" not in uri


# =============================================================================
# QR Code Tests
# =============================================================================

class TestQRGeneration:
    """Tests for QR code generation."""

    def test_generate_qr_returns_bytes(self):
        """Test QR generation returns PNG bytes."""
        data = "monero:44AFFq5k...?tx_amount=0.1"
        qr_bytes = generate_qr_code(data)
        
        assert isinstance(qr_bytes, bytes)
        assert len(qr_bytes) > 0
        # PNG magic bytes
        assert qr_bytes[:8] == b'\x89PNG\r\n\x1a\n'

    def test_generate_qr_different_sizes(self):
        """Test QR generation with different sizes."""
        data = "test data"
        
        size_256 = generate_qr_code(data, size=256)
        size_512 = generate_qr_code(data, size=512)
        
        # Both should be valid PNGs
        assert size_256[:8] == b'\x89PNG\r\n\x1a\n'
        assert size_512[:8] == b'\x89PNG\r\n\x1a\n'

    def test_generate_qr_empty_data_raises(self):
        """Test empty data raises ValueError."""
        with pytest.raises(ValueError, match="cannot be empty"):
            generate_qr_code("")

    def test_generate_payment_qr(self):
        """Test convenience function for payment QR."""
        qr_bytes = generate_payment_qr(
            address="44AFFq5k...",
            amount_xmr="0.123456789012",
            tx_description="Test"
        )
        
        assert isinstance(qr_bytes, bytes)
        assert qr_bytes[:8] == b'\x89PNG\r\n\x1a\n'

    def test_qr_size_for_data(self):
        """Test QR size recommendation."""
        # Short data
        assert get_qr_size_for_data("short") == 256
        
        # Medium data (typical Monero URI)
        medium = "monero:" + "a" * 95 + "?tx_amount=0.123456789012"
        assert get_qr_size_for_data(medium) == 512
        
        # Long data
        long_data = "a" * 300
        assert get_qr_size_for_data(long_data) == 768


# =============================================================================
# Rate Cache Tests
# =============================================================================

class TestRateCache:
    """Tests for rate caching mechanism."""

    def test_cache_stores_and_retrieves(self):
        """Test cache stores and retrieves rates."""
        cache = RateCache(ttl_seconds=60)
        rate = Decimal("15000.50")
        
        cache.set(rate)
        retrieved = cache.get()
        
        assert retrieved == rate

    def test_cache_expires(self):
        """Test cache expires after TTL."""
        cache = RateCache(ttl_seconds=0.01)  # 10ms TTL
        cache.set(Decimal("15000.00"))
        
        import time
        time.sleep(0.02)  # Wait for expiration
        
        assert cache.get() is None
        assert not cache.is_valid()

    def test_cache_invalidate(self):
        """Test manual cache invalidation."""
        cache = RateCache()
        cache.set(Decimal("15000.00"))
        
        cache.invalidate()
        
        assert cache.get() is None
        assert not cache.is_valid()


# =============================================================================
# Cheque Limits Tests
# =============================================================================

class TestChequeLimits:
    """Tests for cheque creation limits."""

    @pytest.fixture(autouse=True)
    def mock_settings(self):
        """Mock settings for all tests in this class."""
        from xmr_cheque_bot import config
        mock_settings = MagicMock()
        mock_settings.max_active_cheques_per_user = 10
        mock_settings.cheque_ttl_seconds = 3600
        mock_settings.confirmations_final = 6
        with patch.object(config, "_settings", mock_settings):
            yield

    @pytest.mark.asyncio
    async def test_check_cheque_creation_allowed_basic(self):
        """Test basic allowance check passes."""
        with patch("xmr_cheque_bot.cheque_limits.count_active_cheques", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 5  # Below limit of 10
            
            result = await check_cheque_creation_allowed("123456")
            assert result is True

    @pytest.mark.asyncio
    async def test_cheque_limit_error_raised(self):
        """Test ChequeLimitError raised when at max."""
        with patch("xmr_cheque_bot.cheque_limits.count_active_cheques", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 10  # At limit
            
            with pytest.raises(ChequeLimitError) as exc_info:
                await check_cheque_creation_allowed("123456")
            
            assert exc_info.value.user_id == "123456"
            assert exc_info.value.current_count == 10
            assert exc_info.value.max_allowed == 10

    @pytest.mark.asyncio
    async def test_cheque_limit_error_message(self):
        """Test error message contains helpful info."""
        with patch("xmr_cheque_bot.cheque_limits.count_active_cheques", new_callable=AsyncMock) as mock_count:
            mock_count.return_value = 12  # Over limit
            
            with pytest.raises(ChequeLimitError) as exc_info:
                await check_cheque_creation_allowed("123456")
            
            assert "Maximum" in str(exc_info.value)
            assert "10" in str(exc_info.value)

    def test_active_statuses(self):
        """Test active statuses are correctly identified."""
        active = get_active_statuses()
        
        assert ChequeStatus.PENDING in active
        assert ChequeStatus.MEMPOOL in active
        assert ChequeStatus.CONFIRMING in active
        assert ChequeStatus.CONFIRMED not in active
        assert ChequeStatus.EXPIRED not in active
        assert ChequeStatus.CANCELLED not in active

    def test_is_status_active(self):
        """Test status activity checker."""
        assert is_status_active(ChequeStatus.PENDING) is True
        assert is_status_active(ChequeStatus.MEMPOOL) is True
        assert is_status_active(ChequeStatus.CONFIRMING) is True
        assert is_status_active(ChequeStatus.CONFIRMED) is False
        assert is_status_active(ChequeStatus.EXPIRED) is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestChequeCreationIntegration:
    """Integration tests for cheque creation flow."""

    @pytest.mark.asyncio
    async def test_full_cheque_creation_flow(self):
        """Test complete flow: compute amount -> build URI -> generate QR."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("20000.00")
            
            # Step 1: Compute amount
            amount = await compute_cheque_amount(1000)
            
            # Step 2: Build URI
            uri = build_monero_uri(
                address="44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uUNzHwJpYdhkRXdDQYFGAXCAw",
                amount_xmr=amount.amount_xmr_display,
            )
            
            # Step 3: Generate QR
            qr_bytes = generate_qr_code(uri)
            
            # Verify chain
            assert amount.amount_atomic_expected > 0
            assert "monero:" in uri
            assert "tx_amount=" in uri
            assert qr_bytes[:8] == b'\x89PNG\r\n\x1a\n'

    @pytest.mark.asyncio
    async def test_amount_uniqueness_with_different_tails(self):
        """Test that different tails produce unique atomic amounts."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("10000.00")
            
            amounts = []
            for tail in [1, 100, 1000, 5000, 9999]:
                result = await compute_cheque_amount(500, tail=tail)
                amounts.append(result.amount_atomic_expected)
            
            # All amounts should be unique
            assert len(set(amounts)) == len(amounts)

    @pytest.mark.asyncio  
    async def test_display_amount_matches_atomic(self):
        """Test that display amount correctly represents atomic units."""
        with patch("xmr_cheque_bot.amount.fetch_xmr_rub_rate", new_callable=AsyncMock) as mock_rate:
            mock_rate.return_value = Decimal("15000.00")
            
            result = await compute_cheque_amount(1500, tail=1234)
            
            # Convert display back to atomic and verify
            display_decimal = Decimal(result.amount_xmr_display)
            reconstructed_atomic = xmr_to_atomic(display_decimal)
            
            assert reconstructed_atomic == result.amount_atomic_expected
