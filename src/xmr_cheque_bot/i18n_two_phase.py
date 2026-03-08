"""Updated i18n messages for two-phase cheque system UX.

Adds new message keys for:
- Rate fixed at payment time explanation
- Invoice expiry countdown
- Refresh option for expired invoices
"""

from xmr_cheque_bot.i18n import I18nKeys, TRANSLATIONS


# =============================================================================
# New i18n Keys for Two-phase System
# =============================================================================

class TwoPhaseI18nKeys:
    """Additional i18n keys for two-phase system."""

    # Seller messages (creating cheque)
    OFFER_CREATED_TITLE = "offer.created.title"
    OFFER_CREATED_RATE_INFO = "offer.created.rate_info"
    OFFER_CREATED_SHARE = "offer.created.share"

    # Payer messages (viewing offer)
    OFFER_VIEW_TITLE = "offer.view.title"
    OFFER_VIEW_AMOUNT_RUB = "offer.view.amount_rub"
    OFFER_VIEW_APPROXIMATE_XMR = "offer.view.approximate_xmr"
    OFFER_VIEW_RATE_FIXED_ON_PAY = "offer.view.rate_fixed_on_pay"
    OFFER_VIEW_PAY_BUTTON = "offer.view.pay_button"
    OFFER_VIEW_EXPIRES_IN = "offer.view.expires_in"

    # Invoice messages (after clicking Pay)
    INVOICE_GENERATED_TITLE = "invoice.generated.title"
    INVOICE_PAY_EXACT_AMOUNT = "invoice.pay_exact_amount"
    INVOICE_RATE_FIXED = "invoice.rate_fixed"
    INVOICE_VALID_FOR = "invoice.valid_for"
    INVOICE_QR_INSTRUCTIONS = "invoice.qr_instructions"
    INVOICE_COUNTDOWN_MINUTES = "invoice.countdown.minutes"
    INVOICE_COUNTDOWN_SECONDS = "invoice.countdown.seconds"

    # Invoice expired messages
    INVOICE_EXPIRED_TITLE = "invoice.expired.title"
    INVOICE_EXPIRED_MESSAGE = "invoice.expired.message"
    INVOICE_EXPIRED_RATE_CHANGED = "invoice.expired.rate_changed"
    INVOICE_EXPIRED_REFRESH_BUTTON = "invoice.expired.refresh_button"

    # Invoice refresh messages
    INVOICE_REFRESHED_TITLE = "invoice.refreshed.title"
    INVOICE_REFRESHED_NEW_AMOUNT = "invoice.refreshed.new_amount"
    INVOICE_REFRESHED_RATE_UPDATED = "invoice.refreshed.rate_updated"

    # Payment status updates
    PAYMENT_DETECTED = "payment.detected"
    INVOICE_PAYMENT_CONFIRMED = "invoice.payment.confirmed"


# =============================================================================
# English Translations
# =============================================================================

TWO_PHASE_EN = {
    # Seller messages
    TwoPhaseI18nKeys.OFFER_CREATED_TITLE: "🎫 Cheque Offer Created",
    TwoPhaseI18nKeys.OFFER_CREATED_RATE_INFO: lambda amount_rub: (
        f"Created cheque for <b>{amount_rub} ₽</b>.\n\n"
        f"The XMR amount will be calculated at the moment of payment using the current exchange rate."
    ),
    TwoPhaseI18nKeys.OFFER_CREATED_SHARE: "Share the link or ID with the payer. They will see the exact XMR amount after clicking 'Pay'.",

    # Payer messages
    TwoPhaseI18nKeys.OFFER_VIEW_TITLE: "💳 Payment Request",
    TwoPhaseI18nKeys.OFFER_VIEW_AMOUNT_RUB: lambda amount_rub: f"Amount: <b>{amount_rub} ₽</b>",
    TwoPhaseI18nKeys.OFFER_VIEW_APPROXIMATE_XMR: lambda approx_xmr: (
        f"Approximately: ~{approx_xmr} XMR (current rate)"
    ),
    TwoPhaseI18nKeys.OFFER_VIEW_RATE_FIXED_ON_PAY: (
        "⚡ <b>The rate will be fixed when you click 'Pay'</b>\n"
        "You'll have 15 minutes to complete the payment after that."
    ),
    TwoPhaseI18nKeys.OFFER_VIEW_PAY_BUTTON: "💰 Pay",
    TwoPhaseI18nKeys.OFFER_VIEW_EXPIRES_IN: lambda minutes: f"⏳ Offer expires in {minutes} minutes",

    # Invoice messages
    TwoPhaseI18nKeys.INVOICE_GENERATED_TITLE: "📋 Payment Invoice Generated",
    TwoPhaseI18nKeys.INVOICE_PAY_EXACT_AMOUNT: lambda exact_xmr: (
        f"<b>Pay exactly:</b> <code>{exact_xmr}</code> XMR"
    ),
    TwoPhaseI18nKeys.INVOICE_RATE_FIXED: lambda rate: (
        f"🔒 Rate fixed: 1 XMR = {rate} ₽"
    ),
    TwoPhaseI18nKeys.INVOICE_VALID_FOR: "⏱ This invoice is valid for 15 minutes",
    TwoPhaseI18nKeys.INVOICE_QR_INSTRUCTIONS: "Scan the QR code or copy the address below:",
    TwoPhaseI18nKeys.INVOICE_COUNTDOWN_MINUTES: lambda minutes: f"⏳ {minutes} minutes remaining",
    TwoPhaseI18nKeys.INVOICE_COUNTDOWN_SECONDS: lambda seconds: f"⏳ {seconds} seconds remaining",

    # Invoice expired
    TwoPhaseI18nKeys.INVOICE_EXPIRED_TITLE: "⏰ Invoice Expired",
    TwoPhaseI18nKeys.INVOICE_EXPIRED_MESSAGE: "More than 15 minutes have passed since the invoice was created.",
    TwoPhaseI18nKeys.INVOICE_EXPIRED_RATE_CHANGED: "The exchange rate may have changed. You can create a new invoice with the current rate.",
    TwoPhaseI18nKeys.INVOICE_EXPIRED_REFRESH_BUTTON: "🔄 Refresh Amount",

    # Invoice refresh
    TwoPhaseI18nKeys.INVOICE_REFRESHED_TITLE: "✅ New Invoice Created",
    TwoPhaseI18nKeys.INVOICE_REFRESHED_NEW_AMOUNT: lambda new_xmr, old_xmr: (
        f"New amount: <code>{new_xmr}</code> XMR\n"
        f"(was: {old_xmr} XMR)"
    ),
    TwoPhaseI18nKeys.INVOICE_REFRESHED_RATE_UPDATED: "Rate updated to current market price.",

    # Payment notifications
    TwoPhaseI18nKeys.PAYMENT_DETECTED: lambda offer_id, amount_rub, tx_hash: (
        f"💸 Payment detected for cheque <code>{offer_id[:8]}</code>!\n"
        f"Amount: {amount_rub} ₽\n"
        f"Transaction: <code>{tx_hash}</code>"
    ),
    TwoPhaseI18nKeys.INVOICE_PAYMENT_CONFIRMED: lambda offer_id, amount_xmr, confirmations: (
        f"✅ Cheque <code>{offer_id[:8]}</code> fully confirmed!\n"
        f"Received: {amount_xmr} XMR\n"
        f"Confirmations: {confirmations}"
    ),
}


# =============================================================================
# Russian Translations
# =============================================================================

TWO_PHASE_RU = {
    # Seller messages
    TwoPhaseI18nKeys.OFFER_CREATED_TITLE: "🎫 Чек создан",
    TwoPhaseI18nKeys.OFFER_CREATED_RATE_INFO: lambda amount_rub: (
        f"Создан чек на <b>{amount_rub} ₽</b>.\n\n"
        f"Сумма в XMR будет рассчитана в момент оплаты по актуальному курсу."
    ),
    TwoPhaseI18nKeys.OFFER_CREATED_SHARE: "Поделитесь ссылкой или ID чека с плательщиком. Он увидит точную сумму в XMR после нажатия кнопки 'Оплатить'.",

    # Payer messages
    TwoPhaseI18nKeys.OFFER_VIEW_TITLE: "💳 Запрос на оплату",
    TwoPhaseI18nKeys.OFFER_VIEW_AMOUNT_RUB: lambda amount_rub: f"Сумма: <b>{amount_rub} ₽</b>",
    TwoPhaseI18nKeys.OFFER_VIEW_APPROXIMATE_XMR: lambda approx_xmr: (
        f"Примерно: ~{approx_xmr} XMR (по текущему курсу)"
    ),
    TwoPhaseI18nKeys.OFFER_VIEW_RATE_FIXED_ON_PAY: (
        "⚡ <b>Курс зафиксируется при нажатии кнопки 'Оплатить'</b>\n"
        "После этого у вас будет 15 минут на оплату."
    ),
    TwoPhaseI18nKeys.OFFER_VIEW_PAY_BUTTON: "💰 Оплатить",
    TwoPhaseI18nKeys.OFFER_VIEW_EXPIRES_IN: lambda minutes: f"⏳ Чек действителен ещё {minutes} минут",

    # Invoice messages
    TwoPhaseI18nKeys.INVOICE_GENERATED_TITLE: "📋 Платёжный инвойс создан",
    TwoPhaseI18nKeys.INVOICE_PAY_EXACT_AMOUNT: lambda exact_xmr: (
        f"<b>Оплатите ровно:</b> <code>{exact_xmr}</code> XMR"
    ),
    TwoPhaseI18nKeys.INVOICE_RATE_FIXED: lambda rate: (
        f"🔒 Курс зафиксирован: 1 XMR = {rate} ₽"
    ),
    TwoPhaseI18nKeys.INVOICE_VALID_FOR: "⏱ Этот инвойс действителен 15 минут",
    TwoPhaseI18nKeys.INVOICE_QR_INSTRUCTIONS: "Отсканируйте QR-код или скопируйте адрес ниже:",
    TwoPhaseI18nKeys.INVOICE_COUNTDOWN_MINUTES: lambda minutes: f"⏳ Осталось {minutes} минут",
    TwoPhaseI18nKeys.INVOICE_COUNTDOWN_SECONDS: lambda seconds: f"⏳ Осталось {seconds} секунд",

    # Invoice expired
    TwoPhaseI18nKeys.INVOICE_EXPIRED_TITLE: "⏰ Инвойс истёк",
    TwoPhaseI18nKeys.INVOICE_EXPIRED_MESSAGE: "Прошло более 15 минут с момента создания инвойса.",
    TwoPhaseI18nKeys.INVOICE_EXPIRED_RATE_CHANGED: "Курс обмена мог измениться. Вы можете создать новый инвойс с актуальным курсом.",
    TwoPhaseI18nKeys.INVOICE_EXPIRED_REFRESH_BUTTON: "🔄 Обновить сумму",

    # Invoice refresh
    TwoPhaseI18nKeys.INVOICE_REFRESHED_TITLE: "✅ Новый инвойс создан",
    TwoPhaseI18nKeys.INVOICE_REFRESHED_NEW_AMOUNT: lambda new_xmr, old_xmr: (
        f"Новая сумма: <code>{new_xmr}</code> XMR\n"
        f"(была: {old_xmr} XMR)"
    ),
    TwoPhaseI18nKeys.INVOICE_REFRESHED_RATE_UPDATED: "Курс обновлён до актуальной рыночной цены.",

    # Payment notifications
    TwoPhaseI18nKeys.PAYMENT_DETECTED: lambda offer_id, amount_rub, tx_hash: (
        f"💸 Обнаружен платёж по чеку <code>{offer_id[:8]}</code>!\n"
        f"Сумма: {amount_rub} ₽\n"
        f"Транзакция: <code>{tx_hash}</code>"
    ),
    TwoPhaseI18nKeys.INVOICE_PAYMENT_CONFIRMED: lambda offer_id, amount_xmr, confirmations: (
        f"✅ Чек <code>{offer_id[:8]}</code> полностью подтверждён!\n"
        f"Получено: {amount_xmr} XMR\n"
        f"Подтверждений: {confirmations}"
    ),
}


def register_two_phase_translations():
    """Register two-phase translations with the main i18n module."""
    TRANSLATIONS["en"].update(TWO_PHASE_EN)
    TRANSLATIONS["ru"].update(TWO_PHASE_RU)
