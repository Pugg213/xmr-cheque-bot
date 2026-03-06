"""Amount computation module for cheque generation.

Converts RUB amounts to XMR atomic units with unique tail to prevent collisions.
Uses Decimal for precision to avoid float drift.
"""

import random
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from xmr_cheque_bot.rates import RateFetchError, fetch_xmr_rub_rate

# Constants
ATOMIC_UNITS_PER_XMR = Decimal("1000000000000")  # 1e12 piconero per XMR
MIN_TAIL = 1
MAX_TAIL = 9999  # Unique tail range (in piconero)


@dataclass(frozen=True)
class ComputedAmount:
    """Result of amount computation for a cheque.

    All fields are deterministic given the inputs and rate.
    The tail ensures unique expected amounts for collision prevention.
    """

    # Input
    amount_rub: int

    # Rate used for conversion
    rate_xmr_rub: Decimal

    # Computed values
    amount_atomic_expected: int  # Exact atomic units to expect (base + tail)
    amount_xmr_display: str  # Human-readable XMR amount (e.g., "0.123456789012")

    # Tail for uniqueness (in piconero)
    tail: int

    # Base amount before tail (for reference)
    base_atomic: int

    def __repr__(self) -> str:
        return (
            f"ComputedAmount("
            f"rub={self.amount_rub}, "
            f"xmr={self.amount_xmr_display}, "
            f"atomic={self.amount_atomic_expected}, "
            f"tail={self.tail}"
            f")"
        )


async def compute_cheque_amount(
    amount_rub: int,
    tail: int | None = None,
) -> ComputedAmount:
    """Compute cheque amount from RUB with unique tail.

    Algorithm:
        1. Fetch current XMR/RUB rate
        2. Calculate XMR amount: amount_rub / rate
        3. Convert to atomic units: xmr * 1e12
        4. Round to nearest integer for base
        5. Add unique tail (1..9999 piconero) for collision prevention
        6. Return exact atomic amount and display string

    Args:
        amount_rub: Amount in Russian rubles (positive integer)
        tail: Optional specific tail value (1..9999), random if not provided

    Returns:
        ComputedAmount with all fields populated

    Raises:
        ValueError: If amount_rub is not positive or tail out of range
        RateFetchError: If exchange rate cannot be fetched

    Example:
        >>> amount = await compute_cheque_amount(1000)
        >>> amount.amount_xmr_display
        '0.001234567891'
        >>> amount.amount_atomic_expected
        1234567891  # base + tail
    """
    if amount_rub <= 0:
        raise ValueError(f"amount_rub must be positive, got {amount_rub}")

    if tail is not None and not (MIN_TAIL <= tail <= MAX_TAIL):
        raise ValueError(f"tail must be between {MIN_TAIL} and {MAX_TAIL}, got {tail}")

    # Fetch current rate
    rate = await fetch_xmr_rub_rate()

    if rate <= 0:
        raise RateFetchError(f"Invalid exchange rate: {rate}")

    # Convert RUB to XMR (as Decimal)
    # xmr = rub / rate
    amount_xmr = Decimal(amount_rub) / rate

    # Convert to atomic units (piconero)
    # atomic = xmr * 1e12 = (rub / rate) * 1e12
    atomic_decimal = amount_xmr * ATOMIC_UNITS_PER_XMR

    # Round to nearest integer for base amount
    # Using ROUND_HALF_UP for predictable behavior
    base_atomic = int(atomic_decimal.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    # Ensure base is non-negative
    if base_atomic < 0:
        base_atomic = 0

    # Generate or use provided tail
    if tail is None:
        tail = random.randint(MIN_TAIL, MAX_TAIL)

    # Calculate final expected amount with tail
    amount_atomic_expected = base_atomic + tail

    # Create display string from exact atomic amount
    # This ensures the payer sees the exact amount that will be checked
    amount_xmr_display = _atomic_to_display(amount_atomic_expected)

    return ComputedAmount(
        amount_rub=amount_rub,
        rate_xmr_rub=rate,
        amount_atomic_expected=amount_atomic_expected,
        amount_xmr_display=amount_xmr_display,
        tail=tail,
        base_atomic=base_atomic,
    )


def _atomic_to_display(atomic_units: int) -> str:
    """Convert atomic units to display string without scientific notation.

    Args:
        atomic_units: Amount in atomic units (piconero)

    Returns:
        Decimal string representation (e.g., "0.123456789012")
    """
    if atomic_units == 0:
        return "0.000000000000"

    # Convert to Decimal and divide by 1e12
    decimal_value = Decimal(atomic_units) / ATOMIC_UNITS_PER_XMR

    # Format with exactly 12 decimal places
    return format(decimal_value, ".12f")


def atomic_to_xmr(atomic_units: int) -> Decimal:
    """Convert atomic units to XMR Decimal.

    Args:
        atomic_units: Amount in atomic units

    Returns:
        Decimal XMR amount
    """
    return Decimal(atomic_units) / ATOMIC_UNITS_PER_XMR


def xmr_to_atomic(xmr_amount: Decimal) -> int:
    """Convert XMR Decimal to atomic units (rounded).

    Args:
        xmr_amount: Amount in XMR as Decimal

    Returns:
        Atomic units as integer (rounded)
    """
    atomic = xmr_amount * ATOMIC_UNITS_PER_XMR
    return int(atomic.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def generate_unique_tail() -> int:
    """Generate a random unique tail value.

    Returns:
        Random integer between MIN_TAIL and MAX_TAIL
    """
    return random.randint(MIN_TAIL, MAX_TAIL)


def validate_tail(tail: int) -> bool:
    """Validate tail is within valid range.

    Args:
        tail: Tail value to validate

    Returns:
        True if valid, False otherwise
    """
    return MIN_TAIL <= tail <= MAX_TAIL
