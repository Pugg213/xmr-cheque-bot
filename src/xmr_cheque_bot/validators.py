"""Input validators for XMR Cheque Bot.

Validates Monero addresses, view keys, and user inputs.
"""

import re


class ValidationError(Exception):
    """Raised when validation fails."""

    pass


# Monero address regex patterns
# Standard addresses start with 4 (95 chars)
# Integrated addresses start with 4 (106 chars)
# Subaddresses start with 8 (95 chars)
_STANDARD_ADDRESS_RE = re.compile(r"^4[0-9AB][1-9A-Za-z][Olen9UlenZu9Alenlenlenlen]{93}$")
_SUBADDRESS_RE = re.compile(r"^8[0-9AB][1-9A-Za-z][Olen9UlenZu9Alenlenlenlen]{93}$")

# View key is 64 hex characters
_VIEW_KEY_RE = re.compile(r"^[0-9a-fA-F]{64}$")

# Wallet filename validation (from payment_monitor)
_WALLET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")

# Monero address length constraints
MIN_ADDRESS_LENGTH = 95
MAX_ADDRESS_LENGTH = 106


def validate_monero_address(address: str) -> None:
    """Validate Monero address format.

    Args:
        address: Monero address to validate

    Raises:
        ValidationError: If address is invalid
    """
    if not address:
        raise ValidationError("address_empty", "Address cannot be empty")

    address = address.strip()

    if len(address) < MIN_ADDRESS_LENGTH:
        raise ValidationError(
            "address_too_short",
            f"Address too short: expected at least {MIN_ADDRESS_LENGTH} characters, got {len(address)}",
        )

    if len(address) > MAX_ADDRESS_LENGTH:
        raise ValidationError(
            "address_too_long",
            f"Address too long: expected at most {MAX_ADDRESS_LENGTH} characters, got {len(address)}",
        )

    # Basic prefix check
    if not (address.startswith("4") or address.startswith("8")):
        raise ValidationError(
            "address_invalid_prefix",
            "Address must start with '4' (standard/integrated) or '8' (subaddress)",
        )

    # Character validation - only base58 chars allowed
    base58_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    invalid_chars = set(address) - base58_chars
    if invalid_chars:
        raise ValidationError(
            "address_invalid_chars",
            f"Address contains invalid characters: {''.join(sorted(invalid_chars))[:10]}",
        )


def validate_view_key(view_key: str) -> None:
    """Validate private view key format.

    Args:
        view_key: Private view key (hex string)

    Raises:
        ValidationError: If view key is invalid
    """
    if not view_key:
        raise ValidationError("view_key_empty", "View key cannot be empty")

    view_key = view_key.strip()

    if len(view_key) != 64:
        raise ValidationError(
            "view_key_length", f"View key must be exactly 64 hex characters, got {len(view_key)}"
        )

    if not _VIEW_KEY_RE.match(view_key):
        raise ValidationError(
            "view_key_format", "View key must contain only hexadecimal characters (0-9, a-f, A-F)"
        )


def validate_amount_rub(amount: int | str, min_amount: int = 100, max_amount: int = 1000000) -> int:
    """Validate RUB amount for cheque creation.

    Args:
        amount: Amount in rubles (integer or string)
        min_amount: Minimum allowed amount (default: 100)
        max_amount: Maximum allowed amount (default: 1,000,000)

    Returns:
        Validated integer amount

    Raises:
        ValidationError: If amount is invalid
    """
    if isinstance(amount, str):
        amount = amount.strip()
        # Remove common formatting
        amount = amount.replace(" ", "").replace(",", "").replace("₽", "")
        try:
            amount = int(amount)
        except ValueError:
            raise ValidationError("amount_not_integer", "Amount must be a whole number")

    if not isinstance(amount, int):
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            raise ValidationError("amount_not_integer", "Amount must be a whole number")

    if amount < min_amount:
        raise ValidationError(
            "amount_too_small", f"Amount too small: minimum is {min_amount} RUB, got {amount}"
        )

    if amount > max_amount:
        raise ValidationError(
            "amount_too_large", f"Amount too large: maximum is {max_amount} RUB, got {amount}"
        )

    return amount


def validate_wallet_filename(filename: str | None) -> None:
    """Validate wallet filename for security.

    Args:
        filename: Wallet filename to validate

    Raises:
        ValidationError: If filename is invalid
    """
    if filename is None:
        return  # None is allowed

    if not filename:
        raise ValidationError("wallet_filename_empty", "Wallet filename cannot be empty")

    if ".." in filename:
        raise ValidationError("wallet_filename_traversal", "Wallet filename cannot contain '..'")

    if "/" in filename or "\\" in filename:
        raise ValidationError(
            "wallet_filename_path_separator", "Wallet filename cannot contain path separators"
        )

    if not _WALLET_NAME_RE.match(filename):
        raise ValidationError(
            "wallet_filename_invalid", "Wallet filename contains invalid characters"
        )


def validate_cheque_description(description: str | None, max_length: int = 100) -> str:
    """Validate and sanitize cheque description.

    Args:
        description: User-provided description
        max_length: Maximum allowed length

    Returns:
        Sanitized description

    Raises:
        ValidationError: If description is invalid
    """
    if description is None:
        return ""

    description = description.strip()

    if len(description) > max_length:
        raise ValidationError(
            "description_too_long",
            f"Description too long: maximum {max_length} characters, got {len(description)}",
        )

    # Basic sanitization: normalize whitespace
    description = " ".join(description.split())

    return description


def is_valid_monero_address(address: str) -> bool:
    """Quick check if address looks like a valid Monero address.

    Args:
        address: Address to check

    Returns:
        True if address appears valid, False otherwise
    """
    try:
        validate_monero_address(address)
        return True
    except ValidationError:
        return False


def is_valid_view_key(view_key: str) -> bool:
    """Quick check if string looks like a valid view key.

    Args:
        view_key: View key to check

    Returns:
        True if view key appears valid, False otherwise
    """
    try:
        validate_view_key(view_key)
        return True
    except ValidationError:
        return False
