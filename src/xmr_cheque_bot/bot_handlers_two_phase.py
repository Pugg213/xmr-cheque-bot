"""Bot handlers for two-phase cheque system UX.

Implements the user-facing flow:
- Seller creates offer (no XMR amount shown)
- Payer views offer with approximate XMR
- Payer clicks "Pay" → Invoice generated with fixed rate
- Invoice expiry countdown and refresh option
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

import structlog
from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from xmr_cheque_bot.storage_two_phase import TwoPhaseStorage, TwoPhaseStorageError
from xmr_cheque_bot.api_two_phase import ChequeOfferAPI, InvoiceAPI
from xmr_cheque_bot.i18n_two_phase import TwoPhaseI18nKeys, register_two_phase_translations
from xmr_cheque_bot.i18n import I18n, get_language_from_telegram_code
from xmr_cheque_bot.redis_schema_two_phase import InvoiceStatus, OfferStatus
from xmr_cheque_bot.uri_qr import generate_payment_qr

logger = structlog.get_logger()

# Register two-phase translations
register_two_phase_translations()

router = Router()


# =============================================================================
# FSM States
# =============================================================================


class TwoPhaseStates(StatesGroup):
    """States for two-phase flow."""

    view_offer = State()  # Payer viewing offer
    pay_invoice = State()  # Payer has invoice, ready to pay
    invoice_expired = State()  # Invoice expired, can refresh


# =============================================================================
# Helper Functions
# =============================================================================


def escape_html(text: str | int | float | None) -> str:
    """Escape HTML special characters."""
    if text is None:
        return ""
    return html.escape(str(text))


def format_countdown(expires_at: datetime) -> str:
    """Format remaining time as countdown string."""
    now = datetime.now(UTC)
    if now >= expires_at:
        return "0 seconds"

    delta = expires_at - now
    total_seconds = int(delta.total_seconds())

    if total_seconds >= 60:
        minutes = total_seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        return f"{total_seconds} second{'s' if total_seconds != 1 else ''}"


def short_id(full_id: str) -> str:
    """Get short ID for display."""
    return full_id.replace("off_", "").replace("inv_", "")[:8]


async def get_user_i18n(storage: TwoPhaseStorage, user_id: str, telegram_lang: str | None = None) -> I18n:
    """Get I18n instance for user."""
    user = await storage.get_user(user_id)
    if user is not None:
        return I18n(user.language)
    return I18n(get_language_from_telegram_code(telegram_lang))


# =============================================================================
# Seller Flow: Create Offer
# =============================================================================


async def handle_create_offer_success(
    message: Message,
    storage: TwoPhaseStorage,
    offer_id: str,
    amount_rub: int,
) -> None:
    """Show success message after offer creation."""
    user_id = str(message.from_user.id)
    i18n = await get_user_i18n(storage, user_id, message.from_user.language_code)

    # Build message
    title = i18n.t(TwoPhaseI18nKeys.OFFER_CREATED_TITLE)
    rate_info = TwoPhaseI18nKeys.OFFER_CREATED_RATE_INFO(amount_rub)
    share_msg = i18n.t(TwoPhaseI18nKeys.OFFER_CREATED_SHARE)

    short = short_id(offer_id)

    text = (
        f"<b>{title}</b>\n\n"
        f"{rate_info}\n\n"
        f"{share_msg}\n\n"
        f"Offer ID: <code>{short}</code>\n"
        f"Link: https://t.me/your_bot?start={offer_id}"
    )

    await message.answer(text, parse_mode=ParseMode.HTML)


# =============================================================================
# Payer Flow: View Offer
# =============================================================================


@router.callback_query(F.data.startswith("offer:view:"))
async def view_offer_callback(callback: CallbackQuery, storage: TwoPhaseStorage) -> None:
    """Handle payer viewing an offer."""
    user_id = str(callback.from_user.id)
    i18n = await get_user_i18n(storage, user_id, callback.from_user.language_code)

    # Parse offer_id from callback data
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid offer", show_alert=True)
        return

    offer_id = parts[2]

    # Get offer
    offer_api = ChequeOfferAPI(storage)
    result = await offer_api.get_offer(offer_id, include_approximate=True)

    if isinstance(result, ErrorResponse):
        await callback.answer(result.error, show_alert=True)
        return

    # Check if offer is still valid
    if result.status != OfferStatus.PENDING.value:
        await callback.answer("This offer is no longer available", show_alert=True)
        return

    # Calculate minutes remaining
    expires_at = datetime.fromisoformat(result.expires_at)
    now = datetime.now(UTC)
    minutes_remaining = max(0, int((expires_at - now).total_seconds() // 60))

    # Build message
    title = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_TITLE)
    amount_line = TwoPhaseI18nKeys.OFFER_VIEW_AMOUNT_RUB(result.amount_rub)

    approx_xmr = result.approximate_xmr or "..."
    approx_line = TwoPhaseI18nKeys.OFFER_VIEW_APPROXIMATE_XMR(approx_xmr)
    rate_info = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_RATE_FIXED_ON_PAY)
    expires_line = TwoPhaseI18nKeys.OFFER_VIEW_EXPIRES_IN(minutes_remaining)

    text = (
        f"<b>{title}</b>\n\n"
        f"{amount_line}\n"
        f"{approx_line}\n\n"
        f"{rate_info}\n\n"
        f"{expires_line}"
    )

    # Build keyboard with Pay button
    builder = InlineKeyboardBuilder()
    pay_button_text = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_PAY_BUTTON)
    builder.button(text=pay_button_text, callback_data=f"offer:pay:{offer_id}")
    builder.adjust(1)

    await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())
    await callback.answer()


# =============================================================================
# Payer Flow: Generate Invoice (Click Pay)
# =============================================================================


@router.callback_query(F.data.startswith("offer:pay:"))
async def pay_offer_callback(callback: CallbackQuery, storage: TwoPhaseStorage) -> None:
    """Handle payer clicking 'Pay' - generate invoice."""
    user_id = str(callback.from_user.id)
    i18n = await get_user_i18n(storage, user_id, callback.from_user.language_code)

    # Parse offer_id
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid offer", show_alert=True)
        return

    offer_id = parts[2]

    # Generate invoice
    invoice_api = InvoiceAPI(storage)
    result = await invoice_api.generate_invoice(offer_id, payer_user_id=user_id)

    if isinstance(result, ErrorResponse):
        if result.code == "OFFER_EXPIRED":
            await callback.answer("This offer has expired", show_alert=True)
        elif result.code == "RATE_FETCH_FAILED":
            await callback.answer("Failed to fetch current rate. Please try again.", show_alert=True)
        else:
            await callback.answer(result.error, show_alert=True)
        return

    # Get offer details for address
    offer = await storage.get_offer(offer_id)
    if offer is None:
        await callback.answer("Offer not found", show_alert=True)
        return

    # Build invoice message
    title = i18n.t(TwoPhaseI18nKeys.INVOICE_GENERATED_TITLE)
    exact_amount = TwoPhaseI18nKeys.INVOICE_PAY_EXACT_AMOUNT(result.amount_xmr)
    rate_line = TwoPhaseI18nKeys.INVOICE_RATE_FIXED(result.rate_xmr_rub)
    valid_for = i18n.t(TwoPhaseI18nKeys.INVOICE_VALID_FOR)
    countdown = TwoPhaseI18nKeys.INVOICE_COUNTDOWN_MINUTES(15)

    text = (
        f"<b>{title}</b>\n\n"
        f"{exact_amount}\n"
        f"{rate_line}\n"
        f"{valid_for}\n"
        f"{countdown}\n\n"
        f"<code>{escape_html(offer.recipient_address)}</code>"
    )

    # Generate QR code
    try:
        qr_bytes = generate_payment_qr(
            address=offer.recipient_address,
            amount_xmr=result.amount_xmr,
            tx_description=offer.description or None,
        )
        photo = BufferedInputFile(qr_bytes, filename="invoice.png")

        # Delete the offer view message and send new invoice message
        await callback.message.delete()
        await callback.message.answer_photo(
            photo=photo,
            caption=text,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.error("invoice_qr_generation_failed", error=str(e))
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML)

    await callback.answer()


# =============================================================================
# Payer Flow: Invoice Expired
# =============================================================================


async def show_invoice_expired(
    message: Message,
    storage: TwoPhaseStorage,
    invoice_id: str,
) -> None:
    """Show expired invoice message with refresh option."""
    user_id = str(message.from_user.id)
    i18n = await get_user_i18n(storage, user_id, message.from_user.language_code)

    title = i18n.t(TwoPhaseI18nKeys.INVOICE_EXPIRED_TITLE)
    expired_msg = i18n.t(TwoPhaseI18nKeys.INVOICE_EXPIRED_MESSAGE)
    rate_changed = i18n.t(TwoPhaseI18nKeys.INVOICE_EXPIRED_RATE_CHANGED)

    text = (
        f"<b>{title}</b>\n\n"
        f"{expired_msg}\n\n"
        f"{rate_changed}"
    )

    # Build keyboard with refresh button
    builder = InlineKeyboardBuilder()
    refresh_text = i18n.t(TwoPhaseI18nKeys.INVOICE_EXPIRED_REFRESH_BUTTON)
    builder.button(text=refresh_text, callback_data=f"invoice:refresh:{invoice_id}")
    builder.adjust(1)

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("invoice:refresh:"))
async def refresh_invoice_callback(callback: CallbackQuery, storage: TwoPhaseStorage) -> None:
    """Handle payer refreshing an expired invoice."""
    user_id = str(callback.from_user.id)
    i18n = await get_user_i18n(storage, user_id, callback.from_user.language_code)

    # Parse invoice_id
    data = callback.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        await callback.answer("Invalid invoice", show_alert=True)
        return

    old_invoice_id = parts[2]

    # Get old invoice for amount comparison
    old_invoice = await storage.get_invoice(old_invoice_id)
    old_xmr = old_invoice.amount_xmr if old_invoice else "?"

    # Refresh invoice
    invoice_api = InvoiceAPI(storage)
    result = await invoice_api.refresh_invoice(old_invoice_id, payer_user_id=user_id)

    if isinstance(result, ErrorResponse):
        await callback.answer(result.error, show_alert=True)
        return

    # Show refreshed invoice
    title = i18n.t(TwoPhaseI18nKeys.INVOICE_REFRESHED_TITLE)
    new_amount = TwoPhaseI18nKeys.INVOICE_REFRESHED_NEW_AMOUNT(result.amount_xmr, old_xmr)
    rate_updated = i18n.t(TwoPhaseI18nKeys.INVOICE_REFRESHED_RATE_UPDATED)

    text = (
        f"<b>{title}</b>\n\n"
        f"{new_amount}\n"
        f"{rate_updated}\n\n"
        f"{TwoPhaseI18nKeys.INVOICE_PAY_EXACT_AMOUNT(result.amount_xmr)}"
    )

    await callback.message.edit_text(text, parse_mode=ParseMode.HTML)
    await callback.answer()


# =============================================================================
# Error Response Helper
# =============================================================================


@dataclass
class ErrorResponse:
    """Error response for API operations."""

    error: str
    code: str
