"""Unit tests for i18n module.

No external calls - pure unit tests.
"""

import pytest

from xmr_cheque_bot.i18n import (
    I18n,
    I18nKeys,
    get_language_from_telegram_code,
    get_status_text,
    get_text,
)


class TestI18nKeys:
    """Tests for i18n key constants."""
    
    def test_keys_are_strings(self) -> None:
        """Test all keys are strings."""
        assert isinstance(I18nKeys.CANCEL, str)
        assert isinstance(I18nKeys.START_WELCOME, str)
        assert isinstance(I18nKeys.WALLET_BIND_SUCCESS, str)
    
    def test_key_uniqueness(self) -> None:
        """Test all key values are unique."""
        keys = [
            I18nKeys.CANCEL,
            I18nKeys.BACK,
            I18nKeys.CONFIRM,
            I18nKeys.ERROR,
            I18nKeys.START_WELCOME,
            I18nKeys.WALLET_BIND_SUCCESS,
            I18nKeys.CHEQUE_CREATE_SUCCESS,
            I18nKeys.PAYMENT_CONFIRMED,
        ]
        assert len(keys) == len(set(keys)), "All keys should be unique"
    
    def test_wallet_viewkey_keys_exist(self) -> None:
        """Test wallet-viewkey safety copy keys exist."""
        # These are critical for M4 requirement
        assert hasattr(I18nKeys, "WALLET_VIEWKEY_WARNING_TITLE")
        assert hasattr(I18nKeys, "WALLET_VIEWKEY_WARNING_TEXT")
        assert hasattr(I18nKeys, "WALLET_VIEWKEY_UNDERSTAND")
        assert hasattr(I18nKeys, "WALLET_VIEWKEY_BACKUP_TITLE")
        assert hasattr(I18nKeys, "WALLET_VIEWKEY_BACKUP_TEXT")
        assert hasattr(I18nKeys, "WALLET_VIEWKEY_NEVER_SHARE")


class TestGetText:
    """Tests for get_text function."""
    
    def test_get_english_text(self) -> None:
        """Test getting English text."""
        result = get_text(I18nKeys.CANCEL, "en")
        assert result == "❌ Cancel"
    
    def test_get_russian_text(self) -> None:
        """Test getting Russian text."""
        result = get_text(I18nKeys.CANCEL, "ru")
        assert result == "❌ Отмена"
    
    def test_unknown_key_returns_key(self) -> None:
        """Test unknown key returns the key itself."""
        result = get_text("unknown.key", "en")
        assert result == "unknown.key"
    
    def test_unknown_language_defaults_to_english(self) -> None:
        """Test unknown language defaults to English."""
        result = get_text(I18nKeys.CANCEL, "fr")
        assert result == "❌ Cancel"
    
    def test_lambda_translation_with_args(self) -> None:
        """Test lambda translation with format arguments."""
        result = get_text(I18nKeys.PAYMENT_CONFIRMED, "en", cid="abc123")
        assert "abc123" in result
        assert "confirmed" in result.lower() or "✅" in result
    
    def test_lambda_translation_russian(self) -> None:
        """Test lambda translation in Russian."""
        result = get_text(I18nKeys.PAYMENT_CONFIRMED, "ru", cid="abc123")
        assert "abc123" in result
    
    def test_lambda_with_multiple_args(self) -> None:
        """Test lambda with multiple arguments."""
        result = get_text(I18nKeys.PAYMENT_CONFIRMING, "en", cid="chq1", conf=3, final=6)
        assert "chq1" in result
        assert "3" in result
        assert "6" in result
    
    def test_string_translation_not_callable(self) -> None:
        """Test string translations are not called as functions."""
        result = get_text(I18nKeys.START_WELCOME, "en")
        assert "Welcome" in result
        assert callable(result) is False


class TestGetStatusText:
    """Tests for get_status_text function."""
    
    def test_pending_status_english(self) -> None:
        """Test pending status in English."""
        result = get_status_text("pending", "en")
        assert "Pending" in result or "⏳" in result
    
    def test_confirmed_status_russian(self) -> None:
        """Test confirmed status in Russian."""
        result = get_status_text("confirmed", "ru")
        assert "✅" in result or "Подтверждён" in result
    
    def test_all_statuses_have_translations(self) -> None:
        """Test all status values have translations."""
        statuses = ["pending", "mempool", "confirming", "confirmed", "expired", "cancelled"]
        for status in statuses:
            en_result = get_status_text(status, "en")
            ru_result = get_status_text(status, "ru")
            assert en_result != status  # Should not return the raw status
            assert ru_result != status
    
    def test_unknown_status_defaults_to_pending(self) -> None:
        """Test unknown status defaults to pending text."""
        result = get_status_text("unknown", "en")
        assert "Pending" in result or "⏳" in result


class TestI18nClass:
    """Tests for I18n convenience class."""
    
    def test_english_instance(self) -> None:
        """Test English I18n instance."""
        i18n = I18n("en")
        assert i18n.t(I18nKeys.CANCEL) == "❌ Cancel"
        assert i18n.lang == "en"
    
    def test_russian_instance(self) -> None:
        """Test Russian I18n instance."""
        i18n = I18n("ru")
        assert i18n.t(I18nKeys.CANCEL) == "❌ Отмена"
        assert i18n.lang == "ru"
    
    def test_invalid_language_defaults_to_english(self) -> None:
        """Test invalid language defaults to English."""
        i18n = I18n("fr")
        assert i18n.lang == "en"
    
    def test_status_method(self) -> None:
        """Test status method."""
        i18n = I18n("en")
        result = i18n.status("confirmed")
        assert "✅" in result or "Confirmed" in result
    
    def test_lambda_with_kwargs(self) -> None:
        """Test lambda translation with kwargs through I18n class."""
        i18n = I18n("en")
        result = i18n.t(I18nKeys.PAYMENT_CONFIRMED, cid="test123")
        assert "test123" in result


class TestGetLanguageFromTelegramCode:
    """Tests for get_language_from_telegram_code function."""
    
    def test_russian_code(self) -> None:
        """Test Russian language code."""
        assert get_language_from_telegram_code("ru") == "ru"
        assert get_language_from_telegram_code("RU") == "ru"
    
    def test_english_code(self) -> None:
        """Test English language code."""
        assert get_language_from_telegram_code("en") == "en"
        assert get_language_from_telegram_code("EN") == "en"
    
    def test_none_defaults_to_english(self) -> None:
        """Test None defaults to English."""
        assert get_language_from_telegram_code(None) == "en"
    
    def test_locale_with_region(self) -> None:
        """Test locale code with region (e.g., en-US)."""
        assert get_language_from_telegram_code("en-US") == "en"
        assert get_language_from_telegram_code("ru-RU") == "ru"
    
    def test_unknown_language_defaults_to_english(self) -> None:
        """Test unknown language defaults to English."""
        assert get_language_from_telegram_code("fr") == "en"
        assert get_language_from_telegram_code("de") == "en"
        assert get_language_from_telegram_code("es") == "en"


class TestWalletViewkeySafetyCopy:
    """Tests for wallet-viewkey safety copy translations (M4 requirement)."""
    
    def test_warning_title_english(self) -> None:
        """Test warning title in English."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_WARNING_TITLE, "en")
        assert "🔐" in result
        assert "Security" in result or "Warning" in result
    
    def test_warning_title_russian(self) -> None:
        """Test warning title in Russian."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_WARNING_TITLE, "ru")
        assert "🔐" in result
        assert "безопасности" in result or "Предупреждение" in result
    
    def test_warning_text_contains_key_points_english(self) -> None:
        """Test warning text contains key security points in English."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_WARNING_TEXT, "en")
        # Should mention view key capabilities
        assert "view key" in result.lower()
        # Should mention it cannot spend
        assert "cannot" in result.lower() or "cannot" in result.lower()
        # Should mention encryption
        assert "encrypt" in result.lower()
        # Should warn about sharing
        assert "never" in result.lower() or "share" in result.lower()
    
    def test_warning_text_contains_key_points_russian(self) -> None:
        """Test warning text contains key security points in Russian."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_WARNING_TEXT, "ru")
        # Should mention view key (ключ просмотра)
        assert "ключ" in result.lower() or "просмотра" in result.lower()
        # Should mention encryption
        assert "шифр" in result.lower() or "зашифр" in result.lower()
    
    def test_understand_button_english(self) -> None:
        """Test 'I understand' button in English."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_UNDERSTAND, "en")
        assert "understand" in result.lower() or "continue" in result.lower()
    
    def test_understand_button_russian(self) -> None:
        """Test 'I understand' button in Russian."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_UNDERSTAND, "ru")
        assert "понимаю" in result.lower() or "продолжить" in result.lower()
    
    def test_backup_title_english(self) -> None:
        """Test backup title in English."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_BACKUP_TITLE, "en")
        assert "Backup" in result or "Important" in result
    
    def test_backup_title_russian(self) -> None:
        """Test backup title in Russian."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_BACKUP_TITLE, "ru")
        assert "резерв" in result.lower() or "копию" in result.lower()
    
    def test_backup_text_mentions_seed_english(self) -> None:
        """Test backup text mentions seed phrase in English."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_BACKUP_TEXT, "en")
        assert "seed" in result.lower() or "phrase" in result.lower()
    
    def test_backup_text_mentions_seed_russian(self) -> None:
        """Test backup text mentions seed phrase in Russian."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_BACKUP_TEXT, "ru")
        assert "сид" in result.lower() or "фраз" in result.lower()
    
    def test_never_share_warning_english(self) -> None:
        """Test never share warning in English."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_NEVER_SHARE, "en")
        assert "never" in result.lower()
        assert "spend key" in result.lower() or "seed" in result.lower()
    
    def test_never_share_warning_russian(self) -> None:
        """Test never share warning in Russian."""
        result = get_text(I18nKeys.WALLET_VIEWKEY_NEVER_SHARE, "ru")
        assert "никогда" in result.lower() or "никому" in result.lower()


class TestAllKeysHaveTranslations:
    """Tests that all defined keys have translations in both languages."""
    
    def test_all_keys_in_english(self) -> None:
        """Test all I18nKeys have English translations."""
        from xmr_cheque_bot.i18n import TRANSLATIONS
        
        en_translations = TRANSLATIONS["en"]
        
        # List of keys to check (sample of important ones)
        keys_to_check = [
            I18nKeys.CANCEL,
            I18nKeys.START_WELCOME,
            I18nKeys.WALLET_BIND_SUCCESS,
            I18nKeys.CHEQUE_CREATE_SUCCESS,
            I18nKeys.PAYMENT_CONFIRMED,
            I18nKeys.ERROR_GENERIC,
        ]
        
        for key in keys_to_check:
            assert key in en_translations, f"Key {key} missing from English translations"
    
    def test_all_keys_in_russian(self) -> None:
        """Test all I18nKeys have Russian translations."""
        from xmr_cheque_bot.i18n import TRANSLATIONS
        
        ru_translations = TRANSLATIONS["ru"]
        
        # List of keys to check (sample of important ones)
        keys_to_check = [
            I18nKeys.CANCEL,
            I18nKeys.START_WELCOME,
            I18nKeys.WALLET_BIND_SUCCESS,
            I18nKeys.CHEQUE_CREATE_SUCCESS,
            I18nKeys.PAYMENT_CONFIRMED,
            I18nKeys.ERROR_GENERIC,
        ]
        
        for key in keys_to_check:
            assert key in ru_translations, f"Key {key} missing from Russian translations"
