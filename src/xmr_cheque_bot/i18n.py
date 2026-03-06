"""Internationalization (i18n) for XMR Cheque Bot.

Supports Russian (ru) and English (en) languages.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class I18nKeys:
    """All i18n keys used in the bot."""

    # Common
    CANCEL = "common.cancel"
    BACK = "common.back"
    CONFIRM = "common.confirm"
    ERROR = "common.error"
    LOADING = "common.loading"
    DONE = "common.done"

    # Start / Language
    START_WELCOME = "start.welcome"
    START_SELECT_LANGUAGE = "start.select_language"
    LANGUAGE_SET = "language.set"

    # Wallet binding
    WALLET_BIND_PROMPT = "wallet.bind.prompt"
    WALLET_BIND_INSTRUCTIONS = "wallet.bind.instructions"
    WALLET_BIND_ENTER_ADDRESS = "wallet.bind.enter_address"
    WALLET_BIND_ENTER_VIEW_KEY = "wallet.bind.enter_view_key"
    WALLET_BIND_CONFIRMATION = "wallet.bind.confirmation"
    WALLET_BIND_SUCCESS = "wallet.bind.success"
    WALLET_BIND_INVALID_ADDRESS = "wallet.bind.invalid_address"
    WALLET_BIND_INVALID_VIEW_KEY = "wallet.bind.invalid_view_key"
    WALLET_BIND_ALREADY_BOUND = "wallet.bind.already_bound"
    WALLET_BIND_RATE_LIMIT = "wallet.bind.rate_limit"

    # Wallet-viewkey safety copy (CRITICAL SECURITY NOTICE)
    WALLET_VIEWKEY_WARNING_TITLE = "wallet.viewkey.warning_title"
    WALLET_VIEWKEY_WARNING_TEXT = "wallet.viewkey.warning_text"
    WALLET_VIEWKEY_UNDERSTAND = "wallet.viewkey.understand"
    WALLET_VIEWKEY_BACKUP_TITLE = "wallet.viewkey.backup_title"
    WALLET_VIEWKEY_BACKUP_TEXT = "wallet.viewkey.backup_text"
    WALLET_VIEWKEY_NEVER_SHARE = "wallet.viewkey.never_share"

    # Create cheque
    CHEQUE_CREATE_PROMPT = "cheque.create.prompt"
    CHEQUE_CREATE_ENTER_AMOUNT = "cheque.create.enter_amount"
    CHEQUE_CREATE_ENTER_DESCRIPTION = "cheque.create.enter_description"
    CHEQUE_CREATE_SUMMARY = "cheque.create.summary"
    CHEQUE_CREATE_SUCCESS = "cheque.create.success"
    CHEQUE_CREATE_RATE_LIMIT = "cheque.create.rate_limit"
    CHEQUE_CREATE_MAX_ACTIVE = "cheque.create.max_active"
    CHEQUE_CREATE_INVALID_AMOUNT = "cheque.create.invalid_amount"

    # Cheque display
    CHEQUE_QR_CAPTION = "cheque.qr_caption"
    CHEQUE_PAY_INSTRUCTIONS = "cheque.pay_instructions"
    CHEQUE_AMOUNT_RUB = "cheque.amount_rub"
    CHEQUE_AMOUNT_XMR = "cheque.amount_xmr"
    CHEQUE_ADDRESS = "cheque.address"
    CHEQUE_EXPIRES_AT = "cheque.expires_at"
    CHEQUE_STATUS = "cheque.status"
    CHEQUE_DESCRIPTION = "cheque.description"

    # Cheque status values
    CHEQUE_STATUS_PENDING = "cheque.status.pending"
    CHEQUE_STATUS_MEMPOOL = "cheque.status.mempool"
    CHEQUE_STATUS_CONFIRMING = "cheque.status.confirming"
    CHEQUE_STATUS_CONFIRMED = "cheque.status.confirmed"
    CHEQUE_STATUS_EXPIRED = "cheque.status.expired"
    CHEQUE_STATUS_CANCELLED = "cheque.status.cancelled"

    # My cheques
    CHEQUE_LIST_EMPTY = "cheque.list.empty"
    CHEQUE_LIST_TITLE = "cheque.list.title"
    CHEQUE_LIST_ITEM = "cheque.list.item"
    CHEQUE_DETAILS = "cheque.details"
    CHEQUE_CANCEL_CONFIRM = "cheque.cancel.confirm"
    CHEQUE_CANCEL_SUCCESS = "cheque.cancel.success"
    CHEQUE_CANCEL_INVALID_STATE = "cheque.cancel.invalid_state"

    # Payment notifications (used by payment_monitor)
    PAYMENT_MEMPOOL = "payment.mempool"
    PAYMENT_CONFIRMING = "payment.confirming"
    PAYMENT_CONFIRMED = "payment.confirmed"

    # Settings
    SETTINGS_TITLE = "settings.title"
    SETTINGS_LANGUAGE = "settings.language"
    SETTINGS_DELETE_DATA = "settings.delete_data"
    SETTINGS_DELETE_DATA_CONFIRM = "settings.delete_data_confirm"
    SETTINGS_DELETE_DATA_SUCCESS = "settings.delete_data_success"
    SETTINGS_DELETE_DATA_CANCELLED = "settings.delete_data_cancelled"

    # Delete data warnings
    DELETE_DATA_WARNING_TITLE = "delete_data.warning_title"
    DELETE_DATA_WARNING_TEXT = "delete_data.warning_text"
    DELETE_DATA_CONFIRM_BUTTON = "delete_data.confirm_button"

    # Errors
    ERROR_GENERIC = "error.generic"
    ERROR_NOT_IMPLEMENTED = "error.not_implemented"
    ERROR_WALLET_NOT_BOUND = "error.wallet_not_bound"
    ERROR_CHEQUE_NOT_FOUND = "error.cheque_not_found"
    ERROR_INVALID_INPUT = "error.invalid_input"


# Translation dictionaries
TRANSLATIONS: dict[str, dict[str, str | Callable]] = {
    "en": {
        # Common
        I18nKeys.CANCEL: "❌ Cancel",
        I18nKeys.BACK: "◀️ Back",
        I18nKeys.CONFIRM: "✅ Confirm",
        I18nKeys.ERROR: "❌ Error",
        I18nKeys.LOADING: "⏳ Loading...",
        I18nKeys.DONE: "✅ Done",
        # Start
        I18nKeys.START_WELCOME: "Welcome to XMR Cheque Bot! 🎫\n\nI help you create Monero payment cheques — shareable payment requests with unique amounts for easy tracking.",
        I18nKeys.START_SELECT_LANGUAGE: "Please select your language:",
        I18nKeys.LANGUAGE_SET: "Language set to English 🇬🇧",
        # Wallet binding
        I18nKeys.WALLET_BIND_PROMPT: "To create cheques, you need to bind your Monero wallet.",
        I18nKeys.WALLET_BIND_INSTRUCTIONS: lambda: (
            "📋 <b>How to get your wallet details:</b>\n\n"
            "1. Open your Monero wallet (GUI, CLI, or mobile)\n"
            "2. Find your <b>primary address</b> (starts with 4)\n"
            "3. Find your <b>private view key</b>\n"
            "   - GUI: Settings → Show seed & keys\n"
            "   - CLI: type 'viewkey'\n"
            "   - Mobile: usually in Settings/Keys\n\n"
            "⚠️ <b>Your view key is sensitive!</b> It allows viewing incoming transactions.\n"
            "It will be encrypted before storage."
        ),
        I18nKeys.WALLET_BIND_ENTER_ADDRESS: "Please send your Monero address (starts with 4 or 8):",
        I18nKeys.WALLET_BIND_ENTER_VIEW_KEY: "Now please send your private view key (64 hex characters):",
        I18nKeys.WALLET_BIND_CONFIRMATION: lambda address: (
            f"Please confirm:\n\nAddress: <code>{address[:16]}...{address[-8:]}</code>\n\nIs this correct?"
        ),
        I18nKeys.WALLET_BIND_SUCCESS: "✅ Wallet bound successfully!\n\nYou can now create cheques.",
        I18nKeys.WALLET_BIND_INVALID_ADDRESS: "❌ Invalid Monero address. Please check and try again.",
        I18nKeys.WALLET_BIND_INVALID_VIEW_KEY: "❌ Invalid view key. It must be 64 hexadecimal characters.",
        I18nKeys.WALLET_BIND_ALREADY_BOUND: "You already have a wallet bound. Use /settings to manage your data.",
        I18nKeys.WALLET_BIND_RATE_LIMIT: "⏳ Please wait a bit before binding another wallet.",
        # Wallet-viewkey safety copy (CRITICAL)
        I18nKeys.WALLET_VIEWKEY_WARNING_TITLE: "🔐 <b>Security Warning</b>",
        I18nKeys.WALLET_VIEWKEY_WARNING_TEXT: (
            "You are about to share your <b>private view key</b>.\n\n"
            "• The view key can see incoming transactions to your wallet\n"
            "• It <b>CANNOT</b> spend your funds\n"
            "• It will be encrypted before storage\n"
            "• Never share your view key publicly\n\n"
            "Do you understand and want to continue?"
        ),
        I18nKeys.WALLET_VIEWKEY_UNDERSTAND: "I understand, continue",
        I18nKeys.WALLET_VIEWKEY_BACKUP_TITLE: "📝 <b>Important: Backup Your Keys</b>",
        I18nKeys.WALLET_VIEWKEY_BACKUP_TEXT: (
            "Before proceeding, ensure you have:\n\n"
            "1. ✅ Backed up your <b>seed phrase</b> (25 words)\n"
            "2. ✅ Written down your <b>spend key</b> (kept secret)\n"
            "3. ✅ Stored backups in a safe place\n\n"
            "Without these, you cannot recover your wallet!"
        ),
        I18nKeys.WALLET_VIEWKEY_NEVER_SHARE: "⚠️ Never share your spend key or seed phrase with anyone!",
        # Create cheque
        I18nKeys.CHEQUE_CREATE_PROMPT: "Let's create a new cheque.",
        I18nKeys.CHEQUE_CREATE_ENTER_AMOUNT: "Enter the amount in Russian Rubles (RUB):\n\nExample: 1000",
        I18nKeys.CHEQUE_CREATE_ENTER_DESCRIPTION: "Add an optional description (or send /skip):",
        I18nKeys.CHEQUE_CREATE_SUMMARY: lambda rub, xmr, desc: (
            f"📋 <b>Cheque Summary</b>\n\n"
            f"Amount: <b>{rub} RUB</b>\n"
            f"≈ {xmr} XMR\n" + (f"Note: {desc}\n" if desc else "") + "\nCreate this cheque?"
        ),
        I18nKeys.CHEQUE_CREATE_SUCCESS: "✅ Cheque created!\n\nShare the QR code or the address below with the payer.",
        I18nKeys.CHEQUE_CREATE_RATE_LIMIT: "⏳ Please wait before creating another cheque.",
        I18nKeys.CHEQUE_CREATE_MAX_ACTIVE: "❌ You have too many active cheques. Cancel some or wait for them to complete.",
        I18nKeys.CHEQUE_CREATE_INVALID_AMOUNT: "❌ Invalid amount. Please enter a number between 100 and 1,000,000 RUB.",
        # Cheque display
        I18nKeys.CHEQUE_QR_CAPTION: "Scan to pay with Monero",
        I18nKeys.CHEQUE_PAY_INSTRUCTIONS: lambda xmr, addr: (
            f"Send exactly <code>{xmr}</code> XMR to:\n<code>{addr}</code>"
        ),
        I18nKeys.CHEQUE_AMOUNT_RUB: "Amount (RUB)",
        I18nKeys.CHEQUE_AMOUNT_XMR: "Amount (XMR)",
        I18nKeys.CHEQUE_ADDRESS: "Address",
        I18nKeys.CHEQUE_EXPIRES_AT: "Expires",
        I18nKeys.CHEQUE_STATUS: "Status",
        I18nKeys.CHEQUE_DESCRIPTION: "Description",
        # Status values
        I18nKeys.CHEQUE_STATUS_PENDING: "⏳ Pending",
        I18nKeys.CHEQUE_STATUS_MEMPOOL: "🌐 In Mempool",
        I18nKeys.CHEQUE_STATUS_CONFIRMING: "⏳ Confirming",
        I18nKeys.CHEQUE_STATUS_CONFIRMED: "✅ Confirmed",
        I18nKeys.CHEQUE_STATUS_EXPIRED: "❌ Expired",
        I18nKeys.CHEQUE_STATUS_CANCELLED: "🚫 Cancelled",
        # My cheques
        I18nKeys.CHEQUE_LIST_EMPTY: "You have no cheques. Create one with /create",
        I18nKeys.CHEQUE_LIST_TITLE: "📋 Your Cheques",
        I18nKeys.CHEQUE_LIST_ITEM: lambda cid, status, rub: f"{status} — {rub} RUB",
        I18nKeys.CHEQUE_DETAILS: "Cheque Details",
        I18nKeys.CHEQUE_CANCEL_CONFIRM: "Are you sure you want to cancel this cheque?",
        I18nKeys.CHEQUE_CANCEL_SUCCESS: "✅ Cheque cancelled.",
        I18nKeys.CHEQUE_CANCEL_INVALID_STATE: "❌ Can only cancel pending cheques.",
        # Payment notifications
        I18nKeys.PAYMENT_MEMPOOL: lambda cid: (
            f"💸 Payment detected for cheque <code>{cid[:8]}</code>! Waiting for confirmations..."
        ),
        I18nKeys.PAYMENT_CONFIRMING: lambda cid, conf, final: (
            f"⏳ Cheque <code>{cid[:8]}</code>: {conf}/{final} confirmations..."
        ),
        I18nKeys.PAYMENT_CONFIRMED: lambda cid: (
            f"✅ Cheque <code>{cid[:8]}</code> fully confirmed! Payment complete."
        ),
        # Settings
        I18nKeys.SETTINGS_TITLE: "⚙️ Settings",
        I18nKeys.SETTINGS_LANGUAGE: "🌐 Language",
        I18nKeys.SETTINGS_DELETE_DATA: "🗑 Delete My Data",
        I18nKeys.SETTINGS_DELETE_DATA_CONFIRM: "⚠️ This will delete all your data including wallet info and cheques. Confirm?",
        I18nKeys.SETTINGS_DELETE_DATA_SUCCESS: "✅ All your data has been deleted.",
        I18nKeys.SETTINGS_DELETE_DATA_CANCELLED: "Deletion cancelled.",
        # Delete data warnings
        I18nKeys.DELETE_DATA_WARNING_TITLE: "⚠️ <b>Warning: Data Deletion</b>",
        I18nKeys.DELETE_DATA_WARNING_TEXT: (
            "You are about to <b>permanently delete</b>:\n\n"
            "• Your wallet binding\n"
            "• All cheques (active and history)\n"
            "• Payment tracking data\n\n"
            "<b>This cannot be undone!</b>\n\n"
            "Your actual Monero funds are safe in your wallet."
        ),
        I18nKeys.DELETE_DATA_CONFIRM_BUTTON: "🗑 Yes, delete everything",
        # Errors
        I18nKeys.ERROR_GENERIC: "❌ Something went wrong. Please try again.",
        I18nKeys.ERROR_NOT_IMPLEMENTED: "🚧 This feature is not yet implemented.",
        I18nKeys.ERROR_WALLET_NOT_BOUND: "❌ No wallet bound. Use /bind to link your wallet first.",
        I18nKeys.ERROR_CHEQUE_NOT_FOUND: "❌ Cheque not found.",
        I18nKeys.ERROR_INVALID_INPUT: "❌ Invalid input. Please try again.",
    },
    "ru": {
        # Common
        I18nKeys.CANCEL: "❌ Отмена",
        I18nKeys.BACK: "◀️ Назад",
        I18nKeys.CONFIRM: "✅ Подтвердить",
        I18nKeys.ERROR: "❌ Ошибка",
        I18nKeys.LOADING: "⏳ Загрузка...",
        I18nKeys.DONE: "✅ Готово",
        # Start
        I18nKeys.START_WELCOME: "Добро пожаловать в XMR Cheque Bot! 🎫\n\nЯ помогаю создавать чеки на оплату Monero — это запросы на оплату с уникальными суммами для удобного отслеживания.",
        I18nKeys.START_SELECT_LANGUAGE: "Пожалуйста, выберите язык:",
        I18nKeys.LANGUAGE_SET: "Язык изменён на русский 🇷🇺",
        # Wallet binding
        I18nKeys.WALLET_BIND_PROMPT: "Для создания чеков нужно привязать Monero-кошелёк.",
        I18nKeys.WALLET_BIND_INSTRUCTIONS: lambda: (
            "📋 <b>Как получить данные кошелька:</b>\n\n"
            "1. Откройте Monero-кошелёк (GUI, CLI или мобильный)\n"
            "2. Найдите <b>основной адрес</b> (начинается с 4)\n"
            "3. Найдите <b>приватный ключ просмотра</b>\n"
            "   - GUI: Настройки → Показать сид и ключи\n"
            "   - CLI: введите 'viewkey'\n"
            "   - Мобильный: обычно в Настройках/Ключах\n\n"
            "⚠️ <b>Ключ просмотра — конфиденциальная информация!</b> Он позволяет видеть входящие транзакции.\n"
            "Он будет зашифрован перед сохранением."
        ),
        I18nKeys.WALLET_BIND_ENTER_ADDRESS: "Отправьте ваш Monero-адрес (начинается с 4 или 8):",
        I18nKeys.WALLET_BIND_ENTER_VIEW_KEY: "Теперь отправьте ваш приватный ключ просмотра (64 шестнадцатеричных символа):",
        I18nKeys.WALLET_BIND_CONFIRMATION: lambda address: (
            f"Пожалуйста, подтвердите:\n\nАдрес: <code>{address[:16]}...{address[-8:]}</code>\n\nВсё верно?"
        ),
        I18nKeys.WALLET_BIND_SUCCESS: "✅ Кошелёк успешно привязан!\n\nТеперь можно создавать чеки.",
        I18nKeys.WALLET_BIND_INVALID_ADDRESS: "❌ Неверный Monero-адрес. Проверьте и попробуйте снова.",
        I18nKeys.WALLET_BIND_INVALID_VIEW_KEY: "❌ Неверный ключ просмотра. Он должен содержать 64 шестнадцатеричных символа.",
        I18nKeys.WALLET_BIND_ALREADY_BOUND: "У вас уже привязан кошелёк. Используйте /settings для управления данными.",
        I18nKeys.WALLET_BIND_RATE_LIMIT: "⏳ Пожалуйста, подождите перед привязкой другого кошелька.",
        # Wallet-viewkey safety copy (CRITICAL)
        I18nKeys.WALLET_VIEWKEY_WARNING_TITLE: "🔐 <b>Предупреждение безопасности</b>",
        I18nKeys.WALLET_VIEWKEY_WARNING_TEXT: (
            "Вы собираетесь предоставить <b>приватный ключ просмотра</b>.\n\n"
            "• Ключ просмотра позволяет видеть входящие транзакции\n"
            "• Он <b>НЕ МОЖЕТ</b> тратить ваши средства\n"
            "• Он будет зашифрован перед сохранением\n"
            "• Никогда не публикуйте ключ просмотра\n\n"
            "Вы понимаете и хотите продолжить?"
        ),
        I18nKeys.WALLET_VIEWKEY_UNDERSTAND: "Я понимаю, продолжить",
        I18nKeys.WALLET_VIEWKEY_BACKUP_TITLE: "📝 <b>Важно: Сделайте резервную копию ключей</b>",
        I18nKeys.WALLET_VIEWKEY_BACKUP_TEXT: (
            "Перед продолжением убедитесь, что у вас есть:\n\n"
            "1. ✅ Резервная копия <b>сид-фразы</b> (25 слов)\n"
            "2. ✅ Записанный <b>ключ траты</b> (хранится в секрете)\n"
            "3. ✅ Резервные копии в надёжном месте\n\n"
            "Без них вы не сможете восстановить кошелёк!"
        ),
        I18nKeys.WALLET_VIEWKEY_NEVER_SHARE: "⚠️ Никогда никому не сообщайте ключ траты и сид-фразу!",
        # Create cheque
        I18nKeys.CHEQUE_CREATE_PROMPT: "Создадим новый чек.",
        I18nKeys.CHEQUE_CREATE_ENTER_AMOUNT: "Введите сумму в российских рублях (₽):\n\nПример: 1000",
        I18nKeys.CHEQUE_CREATE_ENTER_DESCRIPTION: "Добавьте описание (или отправьте /skip):",
        I18nKeys.CHEQUE_CREATE_SUMMARY: lambda rub, xmr, desc: (
            f"📋 <b>Сводка по чеку</b>\n\n"
            f"Сумма: <b>{rub} ₽</b>\n"
            f"≈ {xmr} XMR\n" + (f"Примечание: {desc}\n" if desc else "") + "\nСоздать этот чек?"
        ),
        I18nKeys.CHEQUE_CREATE_SUCCESS: "✅ Чек создан!\n\nПоделитесь QR-кодом или адресом ниже с плательщиком.",
        I18nKeys.CHEQUE_CREATE_RATE_LIMIT: "⏳ Пожалуйста, подождите перед созданием следующего чека.",
        I18nKeys.CHEQUE_CREATE_MAX_ACTIVE: "❌ У вас слишком много активных чеков. Отмените некоторые или дождитесь завершения.",
        I18nKeys.CHEQUE_CREATE_INVALID_AMOUNT: "❌ Неверная сумма. Введите число от 100 до 1 000 000 ₽.",
        # Cheque display
        I18nKeys.CHEQUE_QR_CAPTION: "Отсканируйте для оплаты Monero",
        I18nKeys.CHEQUE_PAY_INSTRUCTIONS: lambda xmr, addr: (
            f"Отправьте ровно <code>{xmr}</code> XMR на:\n<code>{addr}</code>"
        ),
        I18nKeys.CHEQUE_AMOUNT_RUB: "Сумма (₽)",
        I18nKeys.CHEQUE_AMOUNT_XMR: "Сумма (XMR)",
        I18nKeys.CHEQUE_ADDRESS: "Адрес",
        I18nKeys.CHEQUE_EXPIRES_AT: "Истекает",
        I18nKeys.CHEQUE_STATUS: "Статус",
        I18nKeys.CHEQUE_DESCRIPTION: "Описание",
        # Status values
        I18nKeys.CHEQUE_STATUS_PENDING: "⏳ Ожидает",
        I18nKeys.CHEQUE_STATUS_MEMPOOL: "🌐 В мемпуле",
        I18nKeys.CHEQUE_STATUS_CONFIRMING: "⏳ Подтверждается",
        I18nKeys.CHEQUE_STATUS_CONFIRMED: "✅ Подтверждён",
        I18nKeys.CHEQUE_STATUS_EXPIRED: "❌ Истёк",
        I18nKeys.CHEQUE_STATUS_CANCELLED: "🚫 Отменён",
        # My cheques
        I18nKeys.CHEQUE_LIST_EMPTY: "У вас нет чеков. Создайте с помощью /create",
        I18nKeys.CHEQUE_LIST_TITLE: "📋 Ваши чеки",
        I18nKeys.CHEQUE_LIST_ITEM: lambda cid, status, rub: f"{status} — {rub} ₽",
        I18nKeys.CHEQUE_DETAILS: "Детали чека",
        I18nKeys.CHEQUE_CANCEL_CONFIRM: "Вы уверены, что хотите отменить этот чек?",
        I18nKeys.CHEQUE_CANCEL_SUCCESS: "✅ Чек отменён.",
        I18nKeys.CHEQUE_CANCEL_INVALID_STATE: "❌ Можно отменять только ожидающие чеки.",
        # Payment notifications
        I18nKeys.PAYMENT_MEMPOOL: lambda cid: (
            f"💸 Обнаружен платёж по чеку <code>{cid[:8]}</code>! Ожидаем подтверждений..."
        ),
        I18nKeys.PAYMENT_CONFIRMING: lambda cid, conf, final: (
            f"⏳ Чек <code>{cid[:8]}</code>: {conf}/{final} подтверждений..."
        ),
        I18nKeys.PAYMENT_CONFIRMED: lambda cid: (
            f"✅ Чек <code>{cid[:8]}</code> полностью подтверждён! Оплата завершена."
        ),
        # Settings
        I18nKeys.SETTINGS_TITLE: "⚙️ Настройки",
        I18nKeys.SETTINGS_LANGUAGE: "🌐 Язык",
        I18nKeys.SETTINGS_DELETE_DATA: "🗑 Удалить мои данные",
        I18nKeys.SETTINGS_DELETE_DATA_CONFIRM: "⚠️ Это удалит все ваши данные, включая кошелёк и чеки. Подтвердить?",
        I18nKeys.SETTINGS_DELETE_DATA_SUCCESS: "✅ Все ваши данные удалены.",
        I18nKeys.SETTINGS_DELETE_DATA_CANCELLED: "Удаление отменено.",
        # Delete data warnings
        I18nKeys.DELETE_DATA_WARNING_TITLE: "⚠️ <b>Внимание: удаление данных</b>",
        I18nKeys.DELETE_DATA_WARNING_TEXT: (
            "Вы собираетесь <b>безвозвратно удалить</b>:\n\n"
            "• Привязку кошелька\n"
            "• Все чеки (активные и историю)\n"
            "• Данные отслеживания платежей\n\n"
            "<b>Это действие нельзя отменить!</b>\n\n"
            "Ваши реальные средства в Monero останутся в кошельке."
        ),
        I18nKeys.DELETE_DATA_CONFIRM_BUTTON: "🗑 Да, удалить всё",
        # Errors
        I18nKeys.ERROR_GENERIC: "❌ Что-то пошло не так. Попробуйте снова.",
        I18nKeys.ERROR_NOT_IMPLEMENTED: "🚧 Эта функция пока не реализована.",
        I18nKeys.ERROR_WALLET_NOT_BOUND: "❌ Кошелёк не привязан. Используйте /bind для привязки кошелька.",
        I18nKeys.ERROR_CHEQUE_NOT_FOUND: "❌ Чек не найден.",
        I18nKeys.ERROR_INVALID_INPUT: "❌ Неверный ввод. Попробуйте снова.",
    },
}


def get_text(key: str, lang: str = "en", **kwargs) -> str:
    """Get translated text for a key.

    Args:
        key: The i18n key
        lang: Language code ('en' or 'ru')
        **kwargs: Format arguments for lambda translations

    Returns:
        Translated text string

    Example:
        >>> get_text(I18nKeys.START_WELCOME, "en")
        'Welcome to XMR Cheque Bot!...'

        >>> get_text(I18nKeys.PAYMENT_CONFIRMED, "ru", cid="abc123")
        '✅ Чек abc123 полностью подтверждён!...'
    """
    # Default to English if language not found
    translations = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

    # Get the translation
    value = translations.get(key)

    # Fallback to English if key not found
    if value is None and lang != "en":
        value = TRANSLATIONS["en"].get(key)

    # Return key itself if not found anywhere
    if value is None:
        return key

    # Call if it's a lambda/function
    if callable(value):
        try:
            return value(**kwargs)
        except TypeError:
            # If kwargs don't match, try without args
            try:
                return value()
            except TypeError:
                return key

    return str(value)


def get_status_text(status: str, lang: str = "en") -> str:
    """Get localized status text.

    Args:
        status: Status string (pending, mempool, etc.)
        lang: Language code

    Returns:
        Localized status text with emoji
    """
    status_map = {
        "pending": I18nKeys.CHEQUE_STATUS_PENDING,
        "mempool": I18nKeys.CHEQUE_STATUS_MEMPOOL,
        "confirming": I18nKeys.CHEQUE_STATUS_CONFIRMING,
        "confirmed": I18nKeys.CHEQUE_STATUS_CONFIRMED,
        "expired": I18nKeys.CHEQUE_STATUS_EXPIRED,
        "cancelled": I18nKeys.CHEQUE_STATUS_CANCELLED,
    }
    key = status_map.get(status, I18nKeys.CHEQUE_STATUS_PENDING)
    return get_text(key, lang)


class I18n:
    """Convenience class for language-aware text retrieval."""

    def __init__(self, lang: str = "en"):
        """Initialize with language.

        Args:
            lang: Language code ('en' or 'ru')
        """
        self.lang = lang if lang in TRANSLATIONS else "en"

    def t(self, key: str, **kwargs) -> str:
        """Get translated text."""
        return get_text(key, self.lang, **kwargs)

    def status(self, status: str) -> str:
        """Get status text."""
        return get_status_text(status, self.lang)


def get_language_from_telegram_code(lang_code: str | None) -> str:
    """Map Telegram language code to bot language.

    Args:
        lang_code: Telegram user language code (e.g., 'ru', 'en')

    Returns:
        Bot language code ('en' or 'ru')
    """
    if lang_code is None:
        return "en"

    lang_code = lang_code.lower().split("-")[0]  # Handle 'en-US' -> 'en'

    if lang_code == "ru":
        return "ru"

    return "en"
