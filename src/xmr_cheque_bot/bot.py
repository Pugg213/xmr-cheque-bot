"""Telegram Bot implementation using aiogram 3.

Provides handlers for:
- /start - Welcome and language selection
- /bind - Wallet binding flow
- /create - Create cheque flow
- /mycheques - List user's cheques
- /settings - Settings and delete data
"""

from __future__ import annotations

import html
from datetime import datetime
from zoneinfo import ZoneInfo

import structlog
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from xmr_cheque_bot.amount import atomic_to_xmr, compute_cheque_amount
from xmr_cheque_bot.config import get_settings
from xmr_cheque_bot.i18n import I18n, I18nKeys, get_language_from_telegram_code
from xmr_cheque_bot.monero_rpc import MoneroWalletRPC
from xmr_cheque_bot.storage import RedisStorage, StorageError
from xmr_cheque_bot.uri_qr import generate_payment_qr
from xmr_cheque_bot.validators import (
    ValidationError,
    validate_amount_rub,
    validate_cheque_description,
    validate_monero_address,
    validate_view_key,
)

logger = structlog.get_logger()

# Create router
router = Router()

# =============================================================================
# HTML Safety Helpers
# =============================================================================


def escape_html(text: str | int | float | None) -> str:
    """Escape HTML special characters to prevent parse_mode=HTML issues.

    Args:
        text: Text to escape

    Returns:
        Escaped text safe for HTML parse_mode
    """
    if text is None:
        return ""
    return html.escape(str(text))


def format_payment_status(i18n: I18n, cheque: Any, confirmations_final: int = 6) -> str:
    """Format payment status with confirmations counter.

    Args:
        i18n: I18n instance
        cheque: Cheque record
        confirmations_final: Number of confirmations for final status

    Returns:
        Formatted status string with emoji
    """
    status = cheque.status
    conf = getattr(cheque, 'confirmations', 0) or 0

    if status.value == "pending":
        return i18n.t(I18nKeys.PAYMENT_STATUS_PENDING)
    elif status.value == "mempool":
        return f"{i18n.t(I18nKeys.PAYMENT_STATUS_MEMPOOL)} (0/{confirmations_final})"
    elif status.value == "confirming":
        return f"{i18n.t(I18nKeys.PAYMENT_STATUS_CONFIRMING)} ({conf}/{confirmations_final})"
    elif status.value == "confirmed":
        return f"{i18n.t(I18nKeys.PAYMENT_STATUS_CONFIRMED)} ({confirmations_final}/{confirmations_final})"
    elif status.value == "expired":
        return i18n.t(I18nKeys.CHEQUE_STATUS_EXPIRED)
    elif status.value == "cancelled":
        return i18n.t(I18nKeys.CHEQUE_STATUS_CANCELLED)
    return i18n.t(I18nKeys.CHEQUE_STATUS_PENDING)


# =============================================================================
# FSM States
# =============================================================================


class BindWalletStates(StatesGroup):
    """States for wallet binding flow."""

    safety_warning = State()
    enter_address = State()
    confirm_address = State()
    enter_view_key = State()
    confirm_binding = State()


class CreateChequeStates(StatesGroup):
    """States for cheque creation flow."""

    enter_amount = State()
    enter_description = State()
    confirm_cheque = State()


class DeleteDataStates(StatesGroup):
    """States for data deletion flow."""

    confirm_deletion = State()


# =============================================================================
# Helper Functions
# =============================================================================


def get_i18n(state: FSMContext | None = None, lang: str = "en") -> I18n:
    """Get I18n instance from state or language."""
    if state is not None:
        # Try to get language from state data
        # This is a simplified version - in practice, fetch from storage
        pass
    return I18n(lang)


_MSK = ZoneInfo("Europe/Moscow")


def fmt_dt_msk(dt: datetime | None) -> str:
    if dt is None:
        return "-"
    try:
        return dt.astimezone(_MSK).strftime("%Y-%m-%d %H:%M MSK")
    except Exception:
        # Fallback: best-effort string
        return str(dt)


def short_cheque_id(cheque_id: str) -> str:
    # Keep it compact for chat UI
    return cheque_id.replace("chq_", "")[:8]


async def resolve_user_cheque_id(storage: RedisStorage, user_id: str, token: str) -> str | None:
    """Resolve a user-provided cheque token to a full cheque_id.

    Accepts:
    - full id like chq_0123abcd...
    - short prefix like 0123abcd (first 8)
    """
    token = (token or "").strip()
    if not token:
        return None

    if token.startswith("chq_"):
        return token

    # Try prefix match within user's recent cheques
    cheques = await storage.list_user_cheques(user_id, limit=50)
    matches = [c.cheque_id for c in cheques if c.cheque_id.replace("chq_", "").startswith(token)]
    if len(matches) == 1:
        return matches[0]
    return None


def build_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """Main reply keyboard with human-friendly labels."""

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔗 Привязать кошелёк"), KeyboardButton(text="🎫 Создать чек")],
            [KeyboardButton(text="📋 Мои чеки"), KeyboardButton(text="⚙️ Настройки")],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )


def build_lang_keyboard() -> InlineKeyboardMarkup:
    """Build language selection keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🇬🇧 English", callback_data="lang:en")
    builder.button(text="🇷🇺 Русский", callback_data="lang:ru")
    builder.adjust(2)
    return builder.as_markup()


def build_cancel_keyboard(i18n: I18n) -> InlineKeyboardMarkup:
    """Build cancel button keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    return builder.as_markup()


def build_amount_quick_select_keyboard(i18n: I18n) -> InlineKeyboardMarkup:
    """Build quick amount selection keyboard."""
    is_ru = i18n.lang == "ru"
    builder = InlineKeyboardBuilder()
    # Quick amount buttons
    builder.button(text="100₽", callback_data="amount:100")
    builder.button(text="500₽", callback_data="amount:500")
    builder.button(text="1000₽", callback_data="amount:1000")
    builder.button(text="5000₽", callback_data="amount:5000")
    builder.adjust(4)
    # Cancel button on new row
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    return builder.as_markup()


def build_confirm_keyboard(i18n: I18n) -> InlineKeyboardMarkup:
    """Build confirm/cancel keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.CONFIRM), callback_data="action:confirm")
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    builder.adjust(2)
    return builder.as_markup()


def build_settings_keyboard(i18n: I18n) -> InlineKeyboardMarkup:
    """Build settings menu keyboard."""
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.SETTINGS_LANGUAGE), callback_data="settings:language")
    builder.button(text=i18n.t(I18nKeys.SETTINGS_DELETE_DATA), callback_data="settings:delete")
    builder.button(text=i18n.t(I18nKeys.BACK), callback_data="action:back")
    builder.adjust(1)
    return builder.as_markup()


def build_cheque_list_keyboard(i18n: I18n, cheques: list) -> InlineKeyboardMarkup:
    """Build inline keyboard with cheque buttons for quick access.

    Args:
        i18n: I18n instance
        cheques: List of cheque records

    Returns:
        Inline keyboard with buttons for each cheque
    """
    is_ru = i18n.lang == "ru"
    builder = InlineKeyboardBuilder()

    for c in cheques[:10]:  # Max 10 buttons
        cid = short_cheque_id(c.cheque_id)
        status_emoji = {
            "pending": "⏳",
            "mempool": "🌐",
            "confirming": "⏳",
            "confirmed": "✅",
            "expired": "❌",
            "cancelled": "🚫",
        }.get(c.status.value, "•")

        text = f"{status_emoji} {c.amount_rub}₽ | ID: {cid}"
        builder.button(text=text, callback_data=f"chq:qr:{c.cheque_id}")

    builder.adjust(1)  # One button per row
    return builder.as_markup()


def build_cheque_actions_keyboard(
    i18n: I18n, cheque_id: str, status: str | None = None
) -> InlineKeyboardMarkup:
    """Inline actions for a specific cheque.

    Args:
        i18n: I18n instance
        cheque_id: Cheque ID
        status: Optional cheque status to conditionally show buttons
    """
    is_ru = i18n.lang == "ru"

    builder = InlineKeyboardBuilder()
    builder.button(
        text=("🔄 QR / детали" if is_ru else "🔄 QR / details"),
        callback_data=f"chq:qr:{cheque_id}",
    )

    # Show Cancel only for pending cheques
    if status == "pending":
        builder.button(
            text=("🚫 Отменить" if is_ru else "🚫 Cancel"),
            callback_data=f"chq:cancel:{cheque_id}",
        )

    # Show Delete only for final statuses
    if status in ("confirmed", "expired", "cancelled"):
        builder.button(
            text=("🗑 Удалить" if is_ru else "🗑 Delete"),
            callback_data=f"chq:delete:{cheque_id}",
        )

    builder.adjust(1)
    return builder.as_markup()


async def get_user_language(
    storage: RedisStorage, user_id: str, telegram_lang: str | None = None
) -> str:
    """Get user's language from storage or Telegram."""
    user = await storage.get_user(user_id)
    if user is not None:
        return user.language
    return get_language_from_telegram_code(telegram_lang)


# =============================================================================
# Command Handlers
# =============================================================================


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Handle /start command."""
    user_id = str(message.from_user.id)
    telegram_lang = message.from_user.language_code

    # Get or create user
    lang = await get_user_language(storage, user_id, telegram_lang)
    user = await storage.get_or_create_user(user_id, lang)
    i18n = I18n(user.language)

    # Clear any existing state
    await state.clear()

    # Deep-link payload support: /start <offer_id>
    payload = ""
    try:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            payload = parts[1].strip()
    except Exception:
        payload = ""

    if payload.startswith("off_"):
        await show_two_phase_offer(message, storage, payload)
        return

    await message.answer(
        i18n.t(I18nKeys.START_WELCOME),
        parse_mode=ParseMode.HTML,
        reply_markup=build_lang_keyboard(),
    )

    # Show main menu keyboard for quick navigation
    await message.answer(
        "Выберите действие в меню ниже.",
        reply_markup=build_main_reply_keyboard(),
    )


# Human-friendly menu buttons (reply keyboard)
@router.message(F.text == "🔗 Привязать кошелёк")
async def menu_bind(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    await state.clear()
    await cmd_bind(message, state, storage)


@router.message(F.text == "🎫 Создать чек")
async def menu_create(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    await state.clear()
    await cmd_create(message, state, storage)


@router.message(F.text == "📋 Мои чеки")
async def menu_mycheques(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    await state.clear()
    await cmd_mycheques(message, storage)


@router.message(F.text == "⚙️ Настройки")
async def menu_settings(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    await state.clear()
    await cmd_settings(message, storage)


@router.message(Command("bind"))
async def cmd_bind(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Handle /bind command - start wallet binding flow."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    # Check if already bound
    if await storage.has_wallet(user_id):
        await message.answer(i18n.t(I18nKeys.WALLET_BIND_ALREADY_BOUND))
        return

    # Check rate limit
    if await storage.check_wallet_bind_rate_limit(user_id):
        await message.answer(i18n.t(I18nKeys.WALLET_BIND_RATE_LIMIT))
        return

    # Start binding flow with safety warning
    await state.set_state(BindWalletStates.safety_warning)

    # Show backup warning first
    await message.answer(
        i18n.t(I18nKeys.WALLET_VIEWKEY_BACKUP_TITLE)
        + "\n\n"
        + i18n.t(I18nKeys.WALLET_VIEWKEY_BACKUP_TEXT)
        + "\n\n"
        + i18n.t(I18nKeys.WALLET_VIEWKEY_NEVER_SHARE),
        parse_mode=ParseMode.HTML,
    )

    # Show view key warning
    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.WALLET_VIEWKEY_UNDERSTAND), callback_data="bind:understand")
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    builder.adjust(1)

    await message.answer(
        i18n.t(I18nKeys.WALLET_VIEWKEY_WARNING_TITLE)
        + "\n\n"
        + i18n.t(I18nKeys.WALLET_VIEWKEY_WARNING_TEXT),
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup(),
    )


@router.message(Command("create"))
async def cmd_create(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Handle /create command - start cheque creation flow."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    # Check if wallet bound
    if not await storage.has_wallet(user_id):
        await message.answer(i18n.t(I18nKeys.ERROR_WALLET_NOT_BOUND))
        return

    # Check rate limit
    if await storage.check_cheque_rate_limit(user_id):
        await message.answer(i18n.t(I18nKeys.CHEQUE_CREATE_RATE_LIMIT))
        return

    # Check max active cheques
    settings = get_settings()
    active_count = await storage.count_active_cheques(user_id)
    if active_count >= settings.max_active_cheques_per_user:
        await message.answer(i18n.t(I18nKeys.CHEQUE_CREATE_MAX_ACTIVE))
        return

    # Start creation flow
    await state.set_state(CreateChequeStates.enter_amount)

    await message.answer(
        i18n.t(I18nKeys.CHEQUE_CREATE_PROMPT)
        + "\n\n"
        + i18n.t(I18nKeys.CHEQUE_CREATE_ENTER_AMOUNT),
        parse_mode=ParseMode.HTML,
        reply_markup=build_amount_quick_select_keyboard(i18n),
    )


@router.message(Command("mycheques"))
async def cmd_mycheques(message: Message, storage: RedisStorage) -> None:
    """Handle /mycheques command - list user's cheques."""
    from xmr_cheque_bot.config import get_settings

    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)
    settings = get_settings()
    confirmations_final = settings.confirmations_final

    cheques = await storage.list_user_cheques(user_id, limit=10)

    if not cheques:
        await message.answer(i18n.t(I18nKeys.CHEQUE_LIST_EMPTY), reply_markup=build_main_reply_keyboard())
        return

    lines = [f"<b>{i18n.t(I18nKeys.CHEQUE_LIST_TITLE)}</b> ({len(cheques)})", ""]

    for c in cheques:
        cid = short_cheque_id(c.cheque_id)
        created = fmt_dt_msk(c.created_at)
        expires = fmt_dt_msk(c.expires_at)
        xmr = escape_html(c.amount_xmr_display) or "?"
        safe_cid = escape_html(cid)

        # Format status with confirmations
        payment_status = format_payment_status(i18n, c, confirmations_final)

        # Build line based on status
        if c.status.value == "pending":
            line = f"⏳ {payment_status} | {c.amount_rub} ₽ | <code>{xmr}</code> XMR | {created} | id <code>{safe_cid}</code>"
            if not c.is_final() and expires != "-":
                line += f" | exp {expires}"
        else:
            conf_str = f"({c.confirmations or 0}/{confirmations_final})" if c.status.value in ("mempool", "confirming", "confirmed") else ""
            line = f"{payment_status} {conf_str} | {c.amount_rub} ₽ | <code>{xmr}</code> XMR | {created} | id <code>{safe_cid}</code>"

        lines.append(line)

    lines.append("")
    lines.append("Управление: /cheque ID /cancel ID /delete ID")

    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=build_cheque_list_keyboard(i18n, cheques),
    )


@router.message(Command("cheque"))
async def cmd_cheque_details(message: Message, storage: RedisStorage) -> None:
    """Show full details for a cheque and re-send QR."""
    from xmr_cheque_bot.config import get_settings

    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)
    settings = get_settings()
    confirmations_final = settings.confirmations_final

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /cheque ID", reply_markup=build_main_reply_keyboard())
        return

    cheque_id = await resolve_user_cheque_id(storage, user_id, parts[1])
    if cheque_id is None:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    cheque = await storage.get_cheque(cheque_id)
    if cheque is None or cheque.user_id != user_id:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    cid = short_cheque_id(cheque.cheque_id)
    safe_cid = escape_html(cid)
    created = fmt_dt_msk(cheque.created_at)
    expires = fmt_dt_msk(cheque.expires_at)
    xmr = cheque.amount_xmr_display or format(atomic_to_xmr(cheque.amount_atomic_expected), ".12f")
    safe_xmr = escape_html(xmr)
    safe_addr = escape_html(cheque.monero_address)

    # Format payment status with confirmations
    payment_status = format_payment_status(i18n, cheque, confirmations_final)

    # Build confirmations display
    conf_display = ""
    if cheque.status.value in ("mempool", "confirming", "confirmed"):
        conf_num = cheque.confirmations or 0
        conf_display = f"{i18n.t(I18nKeys.PAYMENT_CONFIRMATIONS_LABEL)}: {conf_num}/{confirmations_final}\n"

    details = (
        f"<b>{i18n.t(I18nKeys.CHEQUE_DETAILS)}</b>\n\n"
        f"ID: <code>{safe_cid}</code>\n"
        f"Created: {created}\n"
        f"{i18n.t(I18nKeys.CHEQUE_STATUS)}: {payment_status}\n"
        + conf_display +
        f"{i18n.t(I18nKeys.CHEQUE_AMOUNT_RUB)}: <b>{cheque.amount_rub} ₽</b>\n"
        f"{i18n.t(I18nKeys.CHEQUE_AMOUNT_XMR)}: <code>{safe_xmr}</code>\n"
        f"{i18n.t(I18nKeys.CHEQUE_EXPIRES_AT)}: {expires}\n"
        f"{i18n.t(I18nKeys.CHEQUE_ADDRESS)}: <code>{safe_addr}</code>"
    )

    pay_instructions = i18n.t(I18nKeys.CHEQUE_PAY_INSTRUCTIONS, xmr=safe_xmr, addr=safe_addr)

    try:
        qr_bytes = generate_payment_qr(
            address=cheque.monero_address,
            amount_xmr=xmr,
            tx_description=cheque.description or None,
        )
        photo = BufferedInputFile(qr_bytes, filename="cheque.png")
        await message.answer_photo(
            photo=photo,
            caption=details + "\n\n" + pay_instructions,
            parse_mode=ParseMode.HTML,
            reply_markup=build_cheque_actions_keyboard(i18n, cheque.cheque_id, cheque.status.value),
        )
    except Exception as e:
        logger.error("cheque_details_qr_failed", user_id=user_id, cheque_id=cheque.cheque_id, error=str(e))
        await message.answer(
            details + "\n\n" + pay_instructions,
            parse_mode=ParseMode.HTML,
            reply_markup=build_cheque_actions_keyboard(i18n, cheque.cheque_id, cheque.status.value),
        )


@router.message(Command("cancel"))
async def cmd_cancel_cheque(message: Message, storage: RedisStorage) -> None:
    """Cancel a pending cheque."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /cancel ID", reply_markup=build_main_reply_keyboard())
        return

    cheque_id = await resolve_user_cheque_id(storage, user_id, parts[1])
    if cheque_id is None:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    cheque = await storage.get_cheque(cheque_id)
    if cheque is None or cheque.user_id != user_id:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    try:
        await storage.cancel_cheque(cheque_id)
        await message.answer(i18n.t(I18nKeys.CHEQUE_CANCEL_SUCCESS), reply_markup=build_main_reply_keyboard())
    except StorageError:
        await message.answer(i18n.t(I18nKeys.CHEQUE_CANCEL_INVALID_STATE), reply_markup=build_main_reply_keyboard())


@router.message(Command("delete"))
async def cmd_delete_cheque(message: Message, storage: RedisStorage) -> None:
    """Delete a cheque record from history/index."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /delete ID", reply_markup=build_main_reply_keyboard())
        return

    cheque_id = await resolve_user_cheque_id(storage, user_id, parts[1])
    if cheque_id is None:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    try:
        ok = await storage.delete_cheque(user_id=user_id, cheque_id=cheque_id)
    except StorageError:
        await message.answer(
            (
                "Сначала отмените активный чек: /cancel ID (после этого можно /delete)."
                if lang == "ru"
                else "Cancel the active cheque first: /cancel ID (then you can /delete)."
            ),
            reply_markup=build_main_reply_keyboard(),
        )
        return

    if not ok:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    await message.answer(
        "✅ Удалено." if lang == "ru" else "✅ Deleted.",
        reply_markup=build_main_reply_keyboard(),
    )


@router.message(Command("settings"))
async def cmd_settings(message: Message, storage: RedisStorage) -> None:
    """Handle /settings command."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    await message.answer(
        i18n.t(I18nKeys.SETTINGS_TITLE),
        parse_mode=ParseMode.HTML,
        reply_markup=build_settings_keyboard(i18n),
    )


# =============================================================================
# Callback Handlers
# =============================================================================


@router.callback_query(F.data.startswith("chq:"))
async def cheque_action_callback(callback: CallbackQuery, storage: RedisStorage) -> None:
    """Handle inline cheque actions (QR/details, cancel, delete)."""
    from xmr_cheque_bot.config import get_settings

    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)
    settings = get_settings()
    confirmations_final = settings.confirmations_final

    data = callback.data or ""
    # format: chq:<action>:<cheque_id>
    parts = data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Bad action", show_alert=False)
        return

    _prefix, action, cheque_id = parts

    cheque = await storage.get_cheque(cheque_id)
    if cheque is None or cheque.user_id != user_id:
        await callback.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), show_alert=True)
        return

    if action == "qr":
        cid = short_cheque_id(cheque.cheque_id)
        safe_cid = escape_html(cid)
        created = fmt_dt_msk(cheque.created_at)
        expires = fmt_dt_msk(cheque.expires_at)
        xmr = cheque.amount_xmr_display or format(atomic_to_xmr(cheque.amount_atomic_expected), ".12f")
        safe_xmr = escape_html(xmr)
        safe_addr = escape_html(cheque.monero_address)

        # Format payment status with confirmations
        payment_status = format_payment_status(i18n, cheque, confirmations_final)

        # Build confirmations display
        conf_display = ""
        if cheque.status.value in ("mempool", "confirming", "confirmed"):
            conf_num = cheque.confirmations or 0
            conf_display = f"{i18n.t(I18nKeys.PAYMENT_CONFIRMATIONS_LABEL)}: {conf_num}/{confirmations_final}\n"

        details = (
            f"<b>{i18n.t(I18nKeys.CHEQUE_DETAILS)}</b>\n\n"
            f"ID: <code>{safe_cid}</code>\n"
            f"Created: {created}\n"
            f"{i18n.t(I18nKeys.CHEQUE_STATUS)}: {payment_status}\n"
            + conf_display +
            f"{i18n.t(I18nKeys.CHEQUE_AMOUNT_RUB)}: <b>{cheque.amount_rub} ₽</b>\n"
            f"{i18n.t(I18nKeys.CHEQUE_AMOUNT_XMR)}: <code>{safe_xmr}</code>\n"
            f"{i18n.t(I18nKeys.CHEQUE_EXPIRES_AT)}: {expires}\n"
            f"{i18n.t(I18nKeys.CHEQUE_ADDRESS)}: <code>{safe_addr}</code>"
        )

        pay_instructions = i18n.t(I18nKeys.CHEQUE_PAY_INSTRUCTIONS, xmr=safe_xmr, addr=safe_addr)

        try:
            qr_bytes = generate_payment_qr(
                address=cheque.monero_address,
                amount_xmr=xmr,
                tx_description=cheque.description or None,
            )
            photo = BufferedInputFile(qr_bytes, filename="cheque.png")
            await callback.message.answer_photo(
                photo=photo,
                caption=details + "\n\n" + pay_instructions,
                parse_mode=ParseMode.HTML,
                reply_markup=build_cheque_actions_keyboard(i18n, cheque.cheque_id, cheque.status.value),
            )
        except Exception as e:
            logger.error("cheque_action_qr_failed", user_id=user_id, cheque_id=cheque.cheque_id, error=str(e))
            await callback.message.answer(
                details + "\n\n" + pay_instructions,
                parse_mode=ParseMode.HTML,
                reply_markup=build_cheque_actions_keyboard(i18n, cheque.cheque_id, cheque.status.value),
            )

        await callback.answer()
        return

    if action == "cancel":
        try:
            await storage.cancel_cheque(cheque_id)
            await callback.answer(i18n.t(I18nKeys.CHEQUE_CANCEL_SUCCESS), show_alert=False)
        except StorageError:
            await callback.answer(i18n.t(I18nKeys.CHEQUE_CANCEL_INVALID_STATE), show_alert=True)
        return

    if action == "delete":
        try:
            ok = await storage.delete_cheque(user_id=user_id, cheque_id=cheque_id)
        except StorageError:
            await callback.answer(
                ("Сначала отмените активный чек (/cancel)." if lang == "ru" else "Cancel the active cheque first (/cancel)."),
                show_alert=True,
            )
            return

        if not ok:
            await callback.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), show_alert=True)
            return

        await callback.answer("✅" if lang == "ru" else "✅", show_alert=False)
        return

    await callback.answer("Unknown action", show_alert=False)


@router.callback_query(F.data == "lang:en")
async def set_lang_en(callback: CallbackQuery, storage: RedisStorage) -> None:
    """Set language to English."""
    user_id = str(callback.from_user.id)
    user = await storage.get_or_create_user(user_id, "en")
    user.language = "en"
    await storage.save_user(user)

    i18n = I18n("en")
    await callback.message.edit_text(
        i18n.t(I18nKeys.START_WELCOME) + "\n\n" + i18n.t(I18nKeys.LANGUAGE_SET),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "lang:ru")
async def set_lang_ru(callback: CallbackQuery, storage: RedisStorage) -> None:
    """Set language to Russian."""
    user_id = str(callback.from_user.id)
    user = await storage.get_or_create_user(user_id, "ru")
    user.language = "ru"
    await storage.save_user(user)

    i18n = I18n("ru")
    await callback.message.edit_text(
        i18n.t(I18nKeys.START_WELCOME) + "\n\n" + i18n.t(I18nKeys.LANGUAGE_SET),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "bind:understand")
async def bind_understand(
    callback: CallbackQuery, state: FSMContext, storage: RedisStorage
) -> None:
    """User acknowledged view key warning."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    await state.set_state(BindWalletStates.enter_address)

    await callback.message.edit_text(
        i18n.t(I18nKeys.WALLET_BIND_CONFIRM_ADDRESS),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data.startswith("amount:"))
async def quick_amount_selected(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """Handle quick amount selection."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    # Parse amount from callback data (format: amount:100)
    data = callback.data or ""
    try:
        amount_rub = int(data.split(":")[1])
    except (IndexError, ValueError):
        await callback.answer("Invalid amount", show_alert=False)
        return

    # Validate amount
    from xmr_cheque_bot.validators import ValidationError, validate_amount_rub
    try:
        validate_amount_rub(str(amount_rub))
    except ValidationError:
        await callback.answer(i18n.t(I18nKeys.CHEQUE_CREATE_INVALID_AMOUNT), show_alert=True)
        return

    # Store amount
    await state.update_data(amount_rub=amount_rub)
    await state.set_state(CreateChequeStates.enter_description)

    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.SKIP), callback_data="desc:skip")
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    builder.adjust(2)

    await callback.message.edit_text(
        i18n.t(I18nKeys.CHEQUE_CREATE_ENTER_DESCRIPTION),
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "bind:confirm_address")
async def bind_confirm_address(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """User confirmed address, proceed to view key input."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    data = await state.get_data()
    address = data.get("address")

    if not address:
        await state.clear()
        await callback.message.edit_text(i18n.t(I18nKeys.ERROR_GENERIC))
        await callback.answer()
        return

    await state.set_state(BindWalletStates.enter_view_key)

    await callback.message.edit_text(
        i18n.t(I18nKeys.WALLET_BIND_ADDRESS_CONFIRMED, address=address),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "bind:change_address")
async def bind_change_address(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """User wants to change address, go back to address input."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    await state.set_state(BindWalletStates.enter_address)
    await state.update_data(address=None)

    await callback.message.edit_text(
        i18n.t(I18nKeys.WALLET_BIND_CONFIRM_ADDRESS),
        parse_mode=ParseMode.HTML,
    )
    await callback.answer()


@router.callback_query(F.data == "action:cancel")
async def action_cancel(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """Cancel current operation."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    await state.clear()
    await callback.message.edit_text(i18n.t(I18nKeys.CANCEL))
    await callback.answer()


@router.callback_query(F.data == "action:back")
async def action_back(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """Go back to main menu."""
    await state.clear()
    await cmd_start(callback.message, state, storage)
    await callback.answer()


@router.callback_query(F.data == "settings:delete")
async def settings_delete(
    callback: CallbackQuery, state: FSMContext, storage: RedisStorage
) -> None:
    """Show delete data confirmation."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    await state.set_state(DeleteDataStates.confirm_deletion)

    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.DELETE_DATA_CONFIRM_BUTTON), callback_data="delete:confirm")
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    builder.adjust(1)

    await callback.message.edit_text(
        i18n.t(I18nKeys.DELETE_DATA_WARNING_TITLE)
        + "\n\n"
        + i18n.t(I18nKeys.DELETE_DATA_WARNING_TEXT),
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "delete:confirm")
async def delete_confirm(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """Confirm and execute data deletion."""
    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    # Delete all user data
    deleted = await storage.delete_all_user_data(user_id)

    await state.clear()

    await callback.message.edit_text(
        i18n.t(I18nKeys.SETTINGS_DELETE_DATA_SUCCESS)
        + "\n\n"
        + f"Deleted: {deleted['cheques']} cheques, wallet, and profile.",
    )
    await callback.answer()


@router.callback_query(F.data == "settings:language")
async def settings_language(callback: CallbackQuery, storage: RedisStorage) -> None:
    """Show language selection in settings."""
    await callback.message.edit_text(
        "Select language / Выберите язык:",
        reply_markup=build_lang_keyboard(),
    )
    await callback.answer()


# =============================================================================
# Message Handlers (FSM)
# =============================================================================


@router.message(BindWalletStates.enter_address)
async def process_address(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Process address input."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    address = message.text.strip() if message.text else ""

    # Check if user sent view key instead of address (64 hex chars)
    if len(address) == 64 and all(c in "0123456789abcdefABCDEF" for c in address):
        await message.answer(i18n.t(I18nKeys.WALLET_BIND_VIEWKEY_SENT_INSTEAD))
        return

    try:
        validate_monero_address(address)
    except ValidationError:
        await message.answer(i18n.t(I18nKeys.WALLET_BIND_INVALID_ADDRESS))
        return

    # Store address in state and move to confirmation step
    await state.update_data(address=address)
    await state.set_state(BindWalletStates.confirm_address)

    # Show truncated address for confirmation
    safe_addr = escape_html(address[:16]) + "..." + escape_html(address[-8:])

    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(I18nKeys.CONFIRM), callback_data="bind:confirm_address")
    builder.button(text=i18n.t(I18nKeys.CHANGE), callback_data="bind:change_address")
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    builder.adjust(2)

    await message.answer(
        i18n.t(I18nKeys.WALLET_BIND_CONFIRMATION, address=address),
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup(),
    )


@router.message(BindWalletStates.enter_view_key)
async def process_view_key(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Process view key input and complete binding."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    view_key = message.text.strip() if message.text else ""

    try:
        validate_view_key(view_key)
    except ValidationError:
        await message.answer(i18n.t(I18nKeys.WALLET_BIND_INVALID_VIEW_KEY))
        return

    # Get stored address
    data = await state.get_data()
    address = data.get("address")

    if not address:
        await state.clear()
        await message.answer(i18n.t(I18nKeys.ERROR_GENERIC))
        return

    # Generate wallet file name and create wallet via RPC
    wallet_file_name = f"wallet_{user_id}"
    settings = get_settings()

    # IMPORTANT: this password MUST be the one used to create/open the wallet file.
    import secrets

    wallet_password = secrets.token_urlsafe(18)

    try:
        async with MoneroWalletRPC(url=settings.monero_rpc_url) as rpc:
            # NOTE: monero-wallet-rpc `get_height` can require an opened wallet in some configs.
            # For binding we keep it reliable and start from 0; the cheque monitor uses per-cheque min_height.
            restore_height = 0

            # Create view-only wallet on RPC (with password)
            await rpc.generate_from_keys(
                address=address,
                view_key=view_key,
                filename=wallet_file_name,
                password=wallet_password,
                restore_height=restore_height,
            )
            logger.info("wallet_generated_via_rpc", user_id=user_id, restore_height=restore_height)
    except Exception as e:
        logger.error("wallet_rpc_generation_failed", user_id=user_id, error=str(e))
        await state.clear()
        await message.answer(i18n.t(I18nKeys.ERROR_GENERIC))
        return

    # Bind wallet (saves to Redis with encrypted view key + encrypted wallet password)
    try:
        await storage.bind_wallet(
            user_id=user_id,
            address=address,
            view_key=view_key,
            wallet_file_name=wallet_file_name,
            wallet_password=wallet_password,
        )

        await state.clear()
        await message.answer(
            i18n.t(I18nKeys.WALLET_BIND_SUCCESS),
            parse_mode=ParseMode.HTML,
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        logger.error("wallet_bind_failed", user_id=user_id, error=str(e))
        await state.clear()
        await message.answer(i18n.t(I18nKeys.ERROR_GENERIC))


@router.message(CreateChequeStates.enter_amount)
async def process_amount(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Process amount input."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    try:
        amount_rub = validate_amount_rub(message.text)
    except ValidationError:
        await message.answer(i18n.t(I18nKeys.CHEQUE_CREATE_INVALID_AMOUNT))
        return

    # Store amount
    await state.update_data(amount_rub=amount_rub)
    await state.set_state(CreateChequeStates.enter_description)

    builder = InlineKeyboardBuilder()
    builder.button(text="Skip", callback_data="desc:skip")
    builder.button(text=i18n.t(I18nKeys.CANCEL), callback_data="action:cancel")
    builder.adjust(2)

    await message.answer(
        i18n.t(I18nKeys.CHEQUE_CREATE_ENTER_DESCRIPTION),
        parse_mode=ParseMode.HTML,
        reply_markup=builder.as_markup(),
    )


@router.callback_query(F.data == "desc:skip")
async def skip_description(
    callback: CallbackQuery, state: FSMContext, storage: RedisStorage
) -> None:
    """Skip description."""
    await state.update_data(description="")
    await show_cheque_summary(callback, state, storage)


@router.message(CreateChequeStates.enter_description)
async def process_description(message: Message, state: FSMContext, storage: RedisStorage) -> None:
    """Process description input."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    try:
        description = validate_cheque_description(message.text)
    except ValidationError:
        description = ""

    await state.update_data(description=description)

    # Show summary
    await show_cheque_summary(message, state, storage)


async def show_cheque_summary(
    source: Message | CallbackQuery,
    state: FSMContext,
    storage: RedisStorage,
) -> None:
    """Show cheque summary for confirmation."""
    if isinstance(source, CallbackQuery):
        message = source.message
        user_id = str(source.from_user.id)
        lang = await get_user_language(storage, user_id, source.from_user.language_code)
    else:
        message = source
        user_id = str(source.from_user.id)
        lang = await get_user_language(storage, user_id, source.from_user.language_code)

    i18n = I18n(lang)

    data = await state.get_data()
    amount_rub = data.get("amount_rub", 0)
    description = data.get("description", "")

    # Compute approximate XMR amount (for preview only)
    approx_xmr = "?"
    try:
        from decimal import Decimal

        from xmr_cheque_bot.rates import fetch_xmr_rub_rate

        rate = await fetch_xmr_rub_rate()
        approx = Decimal(amount_rub) / Decimal(str(rate))
        approx_xmr = f"{approx:.6f}"
    except Exception as e:
        logger.warning("approx_rate_failed", user_id=user_id, error=str(e))

    await state.update_data(amount_xmr=approx_xmr)

    data = await state.get_data()
    amount_xmr = data.get("amount_xmr", "?")

    await state.set_state(CreateChequeStates.confirm_cheque)

    summary = i18n.t(
        I18nKeys.CHEQUE_CREATE_SUMMARY,
        rub=amount_rub,
        xmr=amount_xmr,
        desc=description,
    )

    if isinstance(source, CallbackQuery):
        await message.edit_text(
            summary,
            parse_mode=ParseMode.HTML,
            reply_markup=build_confirm_keyboard(i18n),
        )
        await source.answer()
    else:
        await message.answer(
            summary,
            parse_mode=ParseMode.HTML,
            reply_markup=build_confirm_keyboard(i18n),
        )


@router.callback_query(CreateChequeStates.confirm_cheque, F.data == "action:confirm")
async def confirm_cheque(callback: CallbackQuery, state: FSMContext, storage: RedisStorage) -> None:
    """Create the cheque after confirmation."""
    from xmr_cheque_bot.redis_schema import ChequeStatus

    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    data = await state.get_data()
    amount_rub = data.get("amount_rub", 0)
    amount_atomic = data.get("amount_atomic", 0)
    amount_xmr = data.get("amount_xmr", "0")
    description = data.get("description", "")

    # Get user's wallet
    wallet = await storage.get_wallet(user_id)
    if wallet is None:
        await callback.message.edit_text(i18n.t(I18nKeys.ERROR_WALLET_NOT_BOUND))
        await state.clear()
        await callback.answer()
        return

    # NOTE: min_height is computed at *invoice generation time* (when payer clicks Pay),
    # so we don't need chain height here.

    try:
        from xmr_cheque_bot.api_two_phase import ChequeOfferAPI, ErrorResponse
        from xmr_cheque_bot.i18n_two_phase import TwoPhaseI18nKeys, register_two_phase_translations

        register_two_phase_translations()

        offer_api = ChequeOfferAPI(storage)  # type: ignore[arg-type]
        res = await offer_api.create_offer(
            seller_user_id=user_id,
            amount_rub=int(amount_rub),
            recipient_address=wallet.monero_address,
            description=description,
        )
        if isinstance(res, ErrorResponse):
            raise RuntimeError(res.error)

        await state.clear()

        # Build deep link
        link = ""
        try:
            me = await callback.bot.get_me()
            if getattr(me, "username", None):
                link = f"https://t.me/{me.username}?start={res.offer_id}"
        except Exception:
            link = ""

        short = res.offer_id.replace("off_", "")[:8]

        title = i18n.t(TwoPhaseI18nKeys.OFFER_CREATED_TITLE)
        rate_info = i18n.t(TwoPhaseI18nKeys.OFFER_CREATED_RATE_INFO, amount_rub=amount_rub)
        share_msg = i18n.t(TwoPhaseI18nKeys.OFFER_CREATED_SHARE)

        text = (
            f"<b>{title}</b>\n\n"
            f"{rate_info}\n\n"
            f"{share_msg}\n\n"
            f"ID: <code>{escape_html(short)}</code>\n"
        )
        if link:
            text += link

        builder = InlineKeyboardBuilder()
        if link:
            builder.button(text="🔗 Открыть", url=link)
        builder.button(text="🚫 Отменить", callback_data=f"offer:cancel:{res.offer_id}")
        builder.adjust(1)

        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())

    except Exception as e:
        logger.error("offer_creation_failed", user_id=user_id, error=str(e))
        await callback.message.edit_text(i18n.t(I18nKeys.ERROR_GENERIC))
        await state.clear()

    await callback.answer()


# =============================================================================
# Two-phase cheque (Offer → Invoice) handlers
# =============================================================================


async def get_reorg_safe_min_height() -> int:
    """Compute a conservative min_height for filtering old transfers."""
    settings = get_settings()
    current_height: int | None = None

    if settings.daemon_rpc_url:
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                url = settings.daemon_rpc_url.rstrip("/") + "/get_height"
                resp = await client.get(url)
                resp.raise_for_status()
                current_height = int(resp.json().get("height", 0))
        except Exception as e:
            logger.warning("daemon_get_height_failed", error=str(e))

    if current_height is None:
        try:
            async with MoneroWalletRPC(url=settings.monero_rpc_url) as rpc:
                current_height = await rpc.get_current_height()
        except Exception as e:
            logger.warning("monero_rpc_get_height_failed", error=str(e))

    # If height unknown, still allow (worst case: 0)
    reorg_buffer = 30
    base_height = int(current_height or 0)
    return max(0, base_height - reorg_buffer)


async def show_two_phase_offer(message: Message, storage: RedisStorage, offer_id: str) -> None:
    from datetime import UTC, datetime

    from xmr_cheque_bot.api_two_phase import ChequeOfferAPI, ErrorResponse
    from xmr_cheque_bot.i18n_two_phase import TwoPhaseI18nKeys, register_two_phase_translations
    from xmr_cheque_bot.redis_schema_two_phase import OfferStatus

    register_two_phase_translations()

    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    api = ChequeOfferAPI(storage)  # type: ignore[arg-type]
    res = await api.get_offer(offer_id, include_approximate=True)

    if isinstance(res, ErrorResponse):
        await message.answer(res.error)
        return

    if res.status != OfferStatus.PENDING.value:
        await message.answer("Этот чек больше недоступен.")
        return

    expires_at = datetime.fromisoformat(res.expires_at)
    minutes_remaining = max(0, int((expires_at - datetime.now(UTC)).total_seconds() // 60))

    title = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_TITLE)
    amount_line = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_AMOUNT_RUB, amount_rub=res.amount_rub)

    approx = res.approximate_xmr or "?"
    approx_line = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_APPROXIMATE_XMR, approx_xmr=approx)
    rate_info = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_RATE_FIXED_ON_PAY)
    expires_line = i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_EXPIRES_IN, minutes=minutes_remaining)

    text = (
        f"<b>{title}</b>\n\n"
        f"{amount_line}\n"
        f"{approx_line}\n\n"
        f"{rate_info}\n\n"
        f"{expires_line}"
    )

    builder = InlineKeyboardBuilder()
    builder.button(text=i18n.t(TwoPhaseI18nKeys.OFFER_VIEW_PAY_BUTTON), callback_data=f"offer:pay:{offer_id}")
    builder.adjust(1)

    await message.answer(text, parse_mode=ParseMode.HTML, reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("offer:cancel:"))
async def cancel_offer_callback(callback: CallbackQuery, storage: RedisStorage) -> None:
    from xmr_cheque_bot.api_two_phase import ChequeOfferAPI, ErrorResponse

    user_id = str(callback.from_user.id)
    offer_id = (callback.data or "").split(":", 2)[-1]

    api = ChequeOfferAPI(storage)  # type: ignore[arg-type]
    res = await api.cancel_offer(offer_id=offer_id, seller_user_id=user_id)

    if isinstance(res, ErrorResponse):
        await callback.answer(res.error, show_alert=True)
        return

    await callback.message.edit_text("✅ Отменено.")
    await callback.answer()


@router.callback_query(F.data.startswith("offer:pay:"))
async def pay_offer_callback(callback: CallbackQuery, storage: RedisStorage) -> None:
    from datetime import UTC, datetime

    from xmr_cheque_bot.api_two_phase import InvoiceAPI, ErrorResponse
    from xmr_cheque_bot.i18n_two_phase import TwoPhaseI18nKeys, register_two_phase_translations

    register_two_phase_translations()

    user_id = str(callback.from_user.id)
    lang = await get_user_language(storage, user_id, callback.from_user.language_code)
    i18n = I18n(lang)

    offer_id = (callback.data or "").split(":", 2)[-1]

    min_height = await get_reorg_safe_min_height()

    api = InvoiceAPI(storage)  # type: ignore[arg-type]
    res = await api.generate_invoice(offer_id=offer_id, payer_user_id=user_id, min_height=min_height)

    if isinstance(res, ErrorResponse):
        await callback.answer(res.error, show_alert=True)
        return

    # Fetch offer address
    offer = await storage.get_offer(offer_id) if hasattr(storage, "get_offer") else None  # type: ignore[attr-defined]
    addr = getattr(offer, "recipient_address", "") if offer else ""

    expires_at = datetime.fromisoformat(res.expires_at)
    minutes_left = max(0, int((expires_at - datetime.now(UTC)).total_seconds() // 60))

    title = i18n.t(TwoPhaseI18nKeys.INVOICE_GENERATED_TITLE)
    exact_amount = i18n.t(TwoPhaseI18nKeys.INVOICE_PAY_EXACT_AMOUNT, exact_xmr=res.amount_xmr)
    rate_line = i18n.t(TwoPhaseI18nKeys.INVOICE_RATE_FIXED, rate=res.rate_xmr_rub)
    valid_for = i18n.t(TwoPhaseI18nKeys.INVOICE_VALID_FOR)
    countdown = i18n.t(TwoPhaseI18nKeys.INVOICE_COUNTDOWN_MINUTES, minutes=minutes_left)

    text = (
        f"<b>{title}</b>\n\n"
        f"{exact_amount}\n"
        f"{rate_line}\n"
        f"{valid_for}\n"
        f"{countdown}\n\n"
        f"<code>{escape_html(addr)}</code>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text=i18n.t(TwoPhaseI18nKeys.INVOICE_EXPIRED_REFRESH_BUTTON), callback_data=f"invoice:refresh:{res.invoice_id}")
    kb.adjust(1)

    try:
        qr_bytes = generate_payment_qr(address=addr, amount_xmr=res.amount_xmr)
        photo = BufferedInputFile(qr_bytes, filename="invoice.png")
        await callback.message.delete()
        await callback.message.answer_photo(photo=photo, caption=text, parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())
    except Exception as e:
        logger.error("invoice_qr_generation_failed", error=str(e))
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())

    await callback.answer()


@router.callback_query(F.data.startswith("invoice:refresh:"))
async def refresh_invoice_callback(callback: CallbackQuery, storage: RedisStorage) -> None:
    from datetime import UTC, datetime

    from xmr_cheque_bot.api_two_phase import InvoiceAPI, ErrorResponse

    user_id = str(callback.from_user.id)
    invoice_id = (callback.data or "").split(":", 2)[-1]

    inv = await storage.get_invoice(invoice_id) if hasattr(storage, "get_invoice") else None  # type: ignore[attr-defined]
    if inv is None:
        await callback.answer("Invoice not found", show_alert=True)
        return

    # If not expired yet — show remaining time
    now = datetime.now(UTC)
    if not inv.is_expired() and getattr(inv, "status", "") != "expired":
        seconds = int((inv.expires_at - now).total_seconds())
        minutes = max(0, seconds // 60)
        await callback.answer(f"Ещё {minutes} мин до истечения", show_alert=True)
        return

    min_height = await get_reorg_safe_min_height()

    api = InvoiceAPI(storage)  # type: ignore[arg-type]
    res = await api.refresh_invoice(invoice_id=invoice_id, payer_user_id=user_id, min_height=min_height)
    if isinstance(res, ErrorResponse):
        await callback.answer(res.error, show_alert=True)
        return

    # Fetch offer address
    offer = await storage.get_offer(res.cheque_offer_id) if hasattr(storage, "get_offer") else None  # type: ignore[attr-defined]
    addr = getattr(offer, "recipient_address", "") if offer else ""

    expires_at = datetime.fromisoformat(res.expires_at)
    minutes_left = max(0, int((expires_at - now).total_seconds() // 60))

    text = (
        f"<b>✅ Новый инвойс создан</b>\n\n"
        f"<b>Оплатите ровно:</b> <code>{escape_html(res.amount_xmr)}</code> XMR\n"
        f"🔒 Курс зафиксирован: 1 XMR = {escape_html(res.rate_xmr_rub)} ₽\n"
        f"⏱ Действителен 15 минут\n"
        f"⏳ Осталось {minutes_left} минут\n\n"
        f"<code>{escape_html(addr)}</code>"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🔄 Обновить сумму", callback_data=f"invoice:refresh:{res.invoice_id}")
    kb.adjust(1)

    try:
        qr_bytes = generate_payment_qr(address=addr, amount_xmr=res.amount_xmr)
        photo = BufferedInputFile(qr_bytes, filename="invoice.png")
        await callback.message.delete()
        await callback.message.answer_photo(photo=photo, caption=text, parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())
    except Exception as e:
        logger.error("invoice_refresh_qr_failed", error=str(e))
        await callback.message.edit_text(text, parse_mode=ParseMode.HTML, reply_markup=kb.as_markup())

    await callback.answer()


# =============================================================================
# Bot Setup
# =============================================================================


def create_bot(token: str) -> Bot:
    """Create Bot instance."""
    return Bot(token=token, parse_mode=ParseMode.HTML)


def create_dispatcher(storage: RedisStorage | None = None) -> Dispatcher:
    """Create Dispatcher with storage."""
    dp = Dispatcher()

    # Provide storage to handlers via middleware/context
    if storage is None:
        storage = RedisStorage()

    dp["storage"] = storage
    dp.include_router(router)

    return dp


async def setup_bot() -> tuple[Bot, Dispatcher]:
    """Setup bot and dispatcher with dependencies."""
    settings = get_settings()

    bot = create_bot(settings.bot_token)
    storage = RedisStorage()
    dp = create_dispatcher(storage)

    return bot, dp
