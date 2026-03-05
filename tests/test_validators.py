"""Unit tests for validators module.

No external calls - pure unit tests.
"""

import pytest

from xmr_cheque_bot.validators import (
    ValidationError,
    is_valid_monero_address,
    is_valid_view_key,
    validate_amount_rub,
    validate_cheque_description,
    validate_monero_address,
    validate_view_key,
    validate_wallet_filename,
)


class TestValidateMoneroAddress:
    """Tests for validate_monero_address function."""
    
    def test_valid_standard_address(self) -> None:
        """Test valid standard address (95 chars, starts with 4)."""
        # Valid Monero address format (base58 encoded)
        address = "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A"
        # Should not raise
        validate_monero_address(address)
    
    def test_valid_subaddress(self) -> None:
        """Test valid subaddress (starts with 8)."""
        # Valid Monero subaddress format (base58, starts with 8, 95 chars)
        # Using valid base58 chars
        address = "8ABC123" + "1" * 88  # Subaddress starts with 8, valid base58
        # Should not raise - valid prefix, length, and base58 chars
        validate_monero_address(address)
    
    def test_empty_address_raises(self) -> None:
        """Test empty address raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_monero_address("")
        assert exc_info.value.args[0] == "address_empty"
    
    def test_none_treated_as_empty(self) -> None:
        """Test None is treated as empty."""
        with pytest.raises(ValidationError):
            validate_monero_address(None)
    
    def test_short_address_raises(self) -> None:
        """Test too short address raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_monero_address("4short")
        assert exc_info.value.args[0] == "address_too_short"
    
    def test_long_address_raises(self) -> None:
        """Test too long address raises ValidationError."""
        long_address = "4" + "A" * 110
        with pytest.raises(ValidationError) as exc_info:
            validate_monero_address(long_address)
        assert exc_info.value.args[0] == "address_too_long"
    
    def test_wrong_prefix_raises(self) -> None:
        """Test address not starting with 4 or 8 raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_monero_address("1" + "A" * 94)
        assert exc_info.value.args[0] == "address_invalid_prefix"
    
    def test_address_with_whitespace_is_stripped(self) -> None:
        """Test address with whitespace is stripped before validation."""
        # Valid format but wrapped in spaces
        address = "  44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A  "
        # Should not raise (base58 chars only)
        validate_monero_address(address)


class TestValidateViewKey:
    """Tests for validate_view_key function."""
    
    def test_valid_view_key(self) -> None:
        """Test valid 64-char hex view key."""
        view_key = "0" * 64
        validate_view_key(view_key)
    
    def test_valid_view_key_with_hex_chars(self) -> None:
        """Test view key with a-f hex chars."""
        view_key = "abcdef" * 10 + "1234"
        validate_view_key(view_key)
    
    def test_valid_view_key_uppercase(self) -> None:
        """Test view key with uppercase hex chars."""
        view_key = "ABCDEF" * 10 + "1234"
        validate_view_key(view_key)
    
    def test_empty_view_key_raises(self) -> None:
        """Test empty view key raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_view_key("")
        assert exc_info.value.args[0] == "view_key_empty"
    
    def test_short_view_key_raises(self) -> None:
        """Test too short view key raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_view_key("0" * 63)
        assert exc_info.value.args[0] == "view_key_length"
    
    def test_long_view_key_raises(self) -> None:
        """Test too long view key raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            validate_view_key("0" * 65)
        assert exc_info.value.args[0] == "view_key_length"
    
    def test_non_hex_chars_raises(self) -> None:
        """Test view key with non-hex characters raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_view_key("g" * 64)  # 'g' is not hex
        assert exc_info.value.args[0] == "view_key_format"
    
    def test_view_key_with_whitespace_is_stripped(self) -> None:
        """Test view key with whitespace is stripped."""
        view_key = "  " + "0" * 64 + "  "
        validate_view_key(view_key)


class TestValidateAmountRub:
    """Tests for validate_amount_rub function."""
    
    def test_valid_integer_amount(self) -> None:
        """Test valid integer amount."""
        result = validate_amount_rub(1000)
        assert result == 1000
    
    def test_valid_string_amount(self) -> None:
        """Test valid string amount."""
        result = validate_amount_rub("1000")
        assert result == 1000
    
    def test_string_with_spaces(self) -> None:
        """Test string amount with spaces is cleaned."""
        result = validate_amount_rub("1 000")
        assert result == 1000
    
    def test_string_with_comma(self) -> None:
        """Test string amount with comma is cleaned."""
        result = validate_amount_rub("1,000")
        assert result == 1000
    
    def test_string_with_ruble_sign(self) -> None:
        """Test string amount with ₽ is cleaned."""
        result = validate_amount_rub("1000₽")
        assert result == 1000
    
    def test_minimum_amount(self) -> None:
        """Test minimum amount boundary."""
        result = validate_amount_rub(100)
        assert result == 100
    
    def test_below_minimum_raises(self) -> None:
        """Test amount below minimum raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_amount_rub(99)
        assert exc_info.value.args[0] == "amount_too_small"
    
    def test_maximum_amount(self) -> None:
        """Test maximum amount boundary."""
        result = validate_amount_rub(1000000)
        assert result == 1000000
    
    def test_above_maximum_raises(self) -> None:
        """Test amount above maximum raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_amount_rub(1000001)
        assert exc_info.value.args[0] == "amount_too_large"
    
    def test_zero_amount_raises(self) -> None:
        """Test zero amount raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_amount_rub(0)
        assert exc_info.value.args[0] == "amount_too_small"
    
    def test_negative_amount_raises(self) -> None:
        """Test negative amount raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_amount_rub(-100)
        assert exc_info.value.args[0] == "amount_too_small"
    
    def test_non_numeric_string_raises(self) -> None:
        """Test non-numeric string raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_amount_rub("abc")
        assert exc_info.value.args[0] == "amount_not_integer"
    
    def test_custom_limits(self) -> None:
        """Test custom min/max limits."""
        result = validate_amount_rub(50, min_amount=10, max_amount=100)
        assert result == 50
    
    def test_custom_min_violation(self) -> None:
        """Test custom minimum violation."""
        with pytest.raises(ValidationError):
            validate_amount_rub(5, min_amount=10)


class TestValidateChequeDescription:
    """Tests for validate_cheque_description function."""
    
    def test_none_returns_empty(self) -> None:
        """Test None returns empty string."""
        result = validate_cheque_description(None)
        assert result == ""
    
    def test_empty_string(self) -> None:
        """Test empty string returns empty."""
        result = validate_cheque_description("")
        assert result == ""
    
    def test_whitespace_only_returns_empty(self) -> None:
        """Test whitespace-only string returns empty."""
        result = validate_cheque_description("   ")
        assert result == ""
    
    def test_valid_description(self) -> None:
        """Test valid description is returned as-is."""
        result = validate_cheque_description("Invoice #123")
        assert result == "Invoice #123"
    
    def test_description_is_stripped(self) -> None:
        """Test description is stripped of leading/trailing whitespace."""
        result = validate_cheque_description("  Invoice  ")
        assert result == "Invoice"
    
    def test_multiple_spaces_normalized(self) -> None:
        """Test multiple spaces are normalized to single space."""
        result = validate_cheque_description("Invoice   #123")
        assert result == "Invoice #123"
    
    def test_description_at_max_length(self) -> None:
        """Test description at max length is accepted."""
        desc = "A" * 100
        result = validate_cheque_description(desc)
        assert result == desc
    
    def test_description_too_long_raises(self) -> None:
        """Test description exceeding max length raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_cheque_description("A" * 101)
        assert exc_info.value.args[0] == "description_too_long"
    
    def test_custom_max_length(self) -> None:
        """Test custom max length."""
        result = validate_cheque_description("Short", max_length=10)
        assert result == "Short"


class TestValidateWalletFilename:
    """Tests for validate_wallet_filename function."""
    
    def test_none_is_allowed(self) -> None:
        """Test None is allowed."""
        validate_wallet_filename(None)  # Should not raise
    
    def test_valid_filename(self) -> None:
        """Test valid wallet filename."""
        validate_wallet_filename("wallet_12345")
        validate_wallet_filename("my-wallet_v2")
        validate_wallet_filename("wallet.test")
    
    def test_empty_string_raises(self) -> None:
        """Test empty string raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_wallet_filename("")
        assert exc_info.value.args[0] == "wallet_filename_empty"
    
    def test_path_traversal_raises(self) -> None:
        """Test path traversal pattern raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_wallet_filename("../etc/passwd")
        assert exc_info.value.args[0] == "wallet_filename_traversal"
    
    def test_forward_slash_raises(self) -> None:
        """Test forward slash raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_wallet_filename("wallet/test")
        assert exc_info.value.args[0] == "wallet_filename_path_separator"
    
    def test_backslash_raises(self) -> None:
        """Test backslash raises."""
        with pytest.raises(ValidationError) as exc_info:
            validate_wallet_filename("wallet\\test")
        assert exc_info.value.args[0] == "wallet_filename_path_separator"


class TestIsValidMoneroAddress:
    """Tests for is_valid_monero_address convenience function."""
    
    def test_valid_address_returns_true(self) -> None:
        """Test valid address returns True."""
        address = "44AFFq5kSiGBoZ4NMDwYtN18obc8AemS33DBLWs3H7otXft3XjrpDtQGv7SqSsaBYBb98uNbr2VBBEt7f2wfn3RVGQBEP3A"
        assert is_valid_monero_address(address) is True
    
    def test_invalid_address_returns_false(self) -> None:
        """Test invalid address returns False."""
        assert is_valid_monero_address("") is False
        assert is_valid_monero_address("invalid") is False
        assert is_valid_monero_address("1" + "A" * 94) is False  # Wrong prefix


class TestIsValidViewKey:
    """Tests for is_valid_view_key convenience function."""
    
    def test_valid_view_key_returns_true(self) -> None:
        """Test valid view key returns True."""
        assert is_valid_view_key("0" * 64) is True
        assert is_valid_view_key("abcdef" * 10 + "1234") is True
    
    def test_invalid_view_key_returns_false(self) -> None:
        """Test invalid view key returns False."""
        assert is_valid_view_key("") is False
        assert is_valid_view_key("0" * 63) is False  # Too short
        assert is_valid_view_key("0" * 65) is False  # Too long
        assert is_valid_view_key("g" * 64) is False  # Invalid chars
