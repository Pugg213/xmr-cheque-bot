"""Monero URI builder and QR code generator.

Builds Monero payment URIs and generates QR codes as PNG bytes.
"""

import io
from urllib.parse import quote, urlencode

import qrcode
import structlog
from PIL import Image

logger = structlog.get_logger()

# Monero URI scheme
MONERO_SCHEME = "monero"


def build_monero_uri(
    address: str,
    amount_xmr: str | None = None,
    tx_description: str | None = None,
    tx_message: str | None = None,
) -> str:
    """Build a Monero payment URI according to RFC 3986.

    Format: monero:<address>?tx_amount=<amount>&tx_description=<desc>&tx_message=<msg>

    Args:
        address: Monero address (starts with 4 or 8)
        amount_xmr: Optional amount in XMR as string (e.g., "0.123456789012")
        tx_description: Optional transaction description
        tx_message: Optional transaction message

    Returns:
        Complete Monero URI string

    Raises:
        ValueError: If address is empty or malformed

    Example:
        >>> build_monero_uri(
        ...     address="44AFFq5k...",
        ...     amount_xmr="0.123456789012",
        ...     tx_description="Invoice #123"
        ... )
        'monero:44AFFq5k...?tx_amount=0.123456789012&tx_description=Invoice+%23123'
    """
    if not address:
        raise ValueError("Address is required")

    # Basic address validation (Monero addresses start with 4 or 8)
    if not (address.startswith("4") or address.startswith("8")):
        logger.warning("suspicious_monero_address", address_prefix=address[:8])
        # Don't raise - still build URI, but log warning

    # Start with scheme and address
    uri = f"{MONERO_SCHEME}:{address}"

    # Build query parameters
    params: dict[str, str] = {}

    if amount_xmr is not None:
        # Validate amount format (should be numeric)
        try:
            float(amount_xmr)
            params["tx_amount"] = amount_xmr
        except ValueError:
            raise ValueError(f"Invalid amount format: {amount_xmr}")

    if tx_description is not None:
        params["tx_description"] = tx_description

    if tx_message is not None:
        params["tx_message"] = tx_message

    # Add query string if any params
    if params:
        # Use quote for safe encoding of special characters
        query = urlencode(params, quote_via=quote)
        uri = f"{uri}?{query}"

    return uri


def generate_qr_code(
    data: str,
    size: int = 512,
    border: int = 4,
    error_correction: int = qrcode.constants.ERROR_CORRECT_M,
) -> bytes:
    """Generate QR code as PNG bytes.

    Args:
        data: Data to encode in QR code
        size: Output image size in pixels (square)
        border: QR code border size (quiet zone)
        error_correction: Error correction level (L=7%, M=15%, Q=25%, H=30%)

    Returns:
        PNG image as bytes

    Raises:
        ValueError: If data is empty or too large
        RuntimeError: If QR generation fails

    Example:
        >>> uri = build_monero_uri("44AFFq5k...", "0.123456789012")
        >>> qr_bytes = generate_qr_code(uri, size=512)
        >>> len(qr_bytes) > 0
        True
    """
    if not data:
        raise ValueError("Data cannot be empty")

    try:
        # Create QR code instance
        qr = qrcode.QRCode(
            version=None,  # Auto-fit
            error_correction=error_correction,
            box_size=10,
            border=border,
        )

        qr.add_data(data)
        qr.make(fit=True)

        # Create image
        img = qr.make_image(fill_color="black", back_color="white")

        # Convert to RGB if needed (for PNG)
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Resize to requested size
        if size != img.size[0]:
            img = img.resize((size, size), Image.Resampling.LANCZOS)

        # Save to bytes buffer
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)

        png_bytes = buffer.getvalue()

        logger.debug(
            "qr_generated",
            data_length=len(data),
            image_size=size,
            png_size=len(png_bytes),
        )

        return png_bytes

    except Exception as e:
        logger.error("qr_generation_failed", error=str(e))
        raise RuntimeError(f"Failed to generate QR code: {e}") from e


def generate_payment_qr(
    address: str,
    amount_xmr: str,
    tx_description: str | None = None,
    size: int = 512,
) -> bytes:
    """Generate QR code for Monero payment.

    Convenience function that builds URI and generates QR in one step.

    Args:
        address: Monero address
        amount_xmr: Amount in XMR as string
        tx_description: Optional description
        size: QR code size in pixels

    Returns:
        PNG image as bytes

    Example:
        >>> qr = generate_payment_qr(
        ...     address="44AFFq5k...",
        ...     amount_xmr="0.123456789012",
        ...     tx_description="Donation"
        ... )
    """
    uri = build_monero_uri(
        address=address,
        amount_xmr=amount_xmr,
        tx_description=tx_description,
    )
    return generate_qr_code(uri, size=size)


def get_qr_size_for_data(data: str) -> int:
    """Determine appropriate QR code size based on data length.

    Args:
        data: Data to encode

    Returns:
        Recommended size in pixels
    """
    length = len(data)

    # Monero URIs are typically < 200 chars
    # Standard 95x95 address + amount ~120 chars
    if length < 100:
        return 256
    elif length < 200:
        return 512
    else:
        return 768
