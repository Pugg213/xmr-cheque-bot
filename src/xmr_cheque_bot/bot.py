"""Telegram Bot implementation using aiogram 3.

Provides handlers for:
- /start - Welcome and language selection
- /bind - Wallet binding flow
- /create - Create cheque flow
- /mycheques - List user's cheques
- /settings - Settings and delete data
"""

from __future__ import annotations

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
    """Main reply keyboard with core commands.

    Uses command buttons so we don't need extra callback routing.
    """

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/bind"), KeyboardButton(text="/create")],
            [KeyboardButton(text="/mycheques"), KeyboardButton(text="/settings")],
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

    await message.answer(
        i18n.t(I18nKeys.START_WELCOME),
        parse_mode=ParseMode.HTML,
        reply_markup=build_lang_keyboard(),
    )

    # Show main command keyboard for quick navigation
    await message.answer(
        "Команды: /bind /create /mycheques /settings",
        reply_markup=build_main_reply_keyboard(),
    )


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
        reply_markup=build_cancel_keyboard(i18n),
    )


@router.message(Command("mycheques"))
async def cmd_mycheques(message: Message, storage: RedisStorage) -> None:
    """Handle /mycheques command - list user's cheques."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    cheques = await storage.list_user_cheques(user_id, limit=10)

    if not cheques:
        await message.answer(i18n.t(I18nKeys.CHEQUE_LIST_EMPTY), reply_markup=build_main_reply_keyboard())
        return

    lines = [i18n.t(I18nKeys.CHEQUE_LIST_TITLE)]
    for c in cheques:
        status_text = i18n.status(c.status.value)
        cid = short_cheque_id(c.cheque_id)
        created = fmt_dt_msk(c.created_at)
        expires = fmt_dt_msk(c.expires_at)
        xmr = c.amount_xmr_display or "?"

        extra: list[str] = []
        if c.tx_hash:
            extra.append(f"tx <code>{c.tx_hash[:8]}</code>")
        if c.confirmations:
            extra.append(f"conf {c.confirmations}")
        if (c.expires_at is not None) and (not c.is_final()):
            extra.append(f"exp {expires}")

        line = (
            f"• {status_text} | {c.amount_rub} ₽ | <code>{xmr}</code> XMR | {created} | id <code>{cid}</code>"
        )
        if extra:
            line += " | " + ", ".join(extra)

        lines.append(line)

    lines.append("")
    lines.append("Управление: /cheque <id> /cancel <id> /delete <id>")

    await message.answer(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=build_main_reply_keyboard(),
    )


@router.message(Command("cheque"))
async def cmd_cheque_details(message: Message, storage: RedisStorage) -> None:
    """Show full details for a cheque and re-send QR."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /cheque <id>", reply_markup=build_main_reply_keyboard())
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
    status_text = i18n.status(cheque.status.value)
    created = fmt_dt_msk(cheque.created_at)
    expires = fmt_dt_msk(cheque.expires_at)
    xmr = cheque.amount_xmr_display or format(atomic_to_xmr(cheque.amount_atomic_expected), ".12f")

    details = (
        f"<b>{i18n.t(I18nKeys.CHEQUE_DETAILS)}</b>\n"
        f"ID: <code>{cid}</code>\n"
        f"Created: {created}\n"
        f"{i18n.t(I18nKeys.CHEQUE_STATUS)}: {status_text}\n"
        f"{i18n.t(I18nKeys.CHEQUE_AMOUNT_RUB)}: <code>{cheque.amount_rub}</code>\n"
        f"{i18n.t(I18nKeys.CHEQUE_AMOUNT_XMR)}: <code>{xmr}</code>\n"
        f"{i18n.t(I18nKeys.CHEQUE_EXPIRES_AT)}: {expires}\n"
        f"{i18n.t(I18nKeys.CHEQUE_ADDRESS)}: <code>{cheque.monero_address}</code>"
    )

    pay_instructions = i18n.t(I18nKeys.CHEQUE_PAY_INSTRUCTIONS, xmr=xmr, addr=cheque.monero_address)

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
            reply_markup=build_main_reply_keyboard(),
        )
    except Exception as e:
        logger.error("cheque_details_qr_failed", user_id=user_id, cheque_id=cheque.cheque_id, error=str(e))
        await message.answer(
            details + "\n\n" + pay_instructions,
            parse_mode=ParseMode.HTML,
            reply_markup=build_main_reply_keyboard(),
        )


@router.message(Command("cancel"))
async def cmd_cancel_cheque(message: Message, storage: RedisStorage) -> None:
    """Cancel a pending cheque."""
    user_id = str(message.from_user.id)
    lang = await get_user_language(storage, user_id, message.from_user.language_code)
    i18n = I18n(lang)

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Usage: /cancel <id>", reply_markup=build_main_reply_keyboard())
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
        await message.answer("Usage: /delete <id>", reply_markup=build_main_reply_keyboard())
        return

    cheque_id = await resolve_user_cheque_id(storage, user_id, parts[1])
    if cheque_id is None:
        await message.answer(i18n.t(I18nKeys.ERROR_CHEQUE_NOT_FOUND), reply_markup=build_main_reply_keyboard())
        return

    ok = await storage.delete_cheque(user_id=user_id, cheque_id=cheque_id)
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
        i18n.t(I18nKeys.WALLET_BIND_INSTRUCTIONS)
        + "\n\n"
        + i18n.t(I18nKeys.WALLET_BIND_ENTER_ADDRESS),
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

    try:
        validate_monero_address(address)
    except ValidationError:
        await message.answer(i18n.t(I18nKeys.WALLET_BIND_INVALID_ADDRESS))
        return

    # Store address in state
    await state.update_data(address=address)
    await state.set_state(BindWalletStates.enter_view_key)

    await message.answer(
        i18n.t(I18nKeys.WALLET_BIND_CONFIRMATION, address=address),
        parse_mode=ParseMode.HTML,
        reply_markup=build_confirm_keyboard(i18n),
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
            # Get current height for restore
            current_height = await rpc.get_current_height()
            restore_height = max(0, current_height - 100)

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

    # Compute XMR amount
    try:
        computed = await compute_cheque_amount(amount_rub)
        await state.update_data(
            amount_atomic=computed.amount_atomic_expected,
            amount_xmr=computed.amount_xmr_display,
        )
    except Exception as e:
        logger.error("amount_computation_failed", user_id=user_id, error=str(e))
        await message.answer(i18n.t(I18nKeys.ERROR_GENERIC))
        await state.clear()
        return

    data = await state.get_data()  # Refresh with computed values
    amount_xmr = data.get("amount_xmr", "0")

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

    # Use actual blockchain height (with small reorg buffer) to filter incoming transfers.
    settings = get_settings()
    try:
        async with MoneroWalletRPC(url=settings.monero_rpc_url) as rpc:
            current_height = await rpc.get_current_height()
    except Exception as e:
        logger.error("monero_rpc_get_height_failed", user_id=user_id, error=str(e))
        await callback.message.edit_text(i18n.t(I18nKeys.ERROR_GENERIC))
        await state.clear()
        await callback.answer()
        return

    reorg_buffer = 30
    min_height = max(0, current_height - reorg_buffer)

    try:
        # Create cheque
        cheque = await storage.create_cheque(
            user_id=user_id,
            amount_rub=amount_rub,
            amount_atomic=amount_atomic,
            amount_xmr_display=amount_xmr,
            monero_address=wallet.monero_address,
            min_height=min_height,
            description=description,
        )

        await state.clear()

        # Send success message
        await callback.message.edit_text(i18n.t(I18nKeys.CHEQUE_CREATE_SUCCESS))

        # Generate and send QR code
        try:
            qr_bytes = generate_payment_qr(
                address=wallet.monero_address,
                amount_xmr=amount_xmr,
                tx_description=description or None,
            )

            pay_instructions = i18n.t(
                I18nKeys.CHEQUE_PAY_INSTRUCTIONS,
                xmr=amount_xmr,
                addr=wallet.monero_address,
            )

            photo = BufferedInputFile(qr_bytes, filename="cheque.png")

            await callback.message.answer_photo(
                photo=photo,
                caption=(
                    i18n.t(I18nKeys.CHEQUE_QR_CAPTION)
                    + "\n\n"
                    + pay_instructions
                    + "\n\n"
                    + f"ID: <code>{short_cheque_id(cheque.cheque_id)}</code>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=build_main_reply_keyboard(),
            )
        except Exception as e:
            logger.error("qr_generation_failed", user_id=user_id, error=str(e))
            # Still show address even if QR fails
            await callback.message.answer(
                i18n.t(
                    I18nKeys.CHEQUE_PAY_INSTRUCTIONS,
                    xmr=amount_xmr,
                    addr=wallet.monero_address,
                )
                + "\n\n"
                + f"ID: <code>{short_cheque_id(cheque.cheque_id)}</code>",
                parse_mode=ParseMode.HTML,
                reply_markup=build_main_reply_keyboard(),
            )

    except Exception as e:
        logger.error("cheque_creation_failed", user_id=user_id, error=str(e))
        await callback.message.edit_text(i18n.t(I18nKeys.ERROR_GENERIC))
        await state.clear()

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
