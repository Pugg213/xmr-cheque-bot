# ARTIFACTS_M4 — Telegram Bot Core (v2)

This milestone implements the Telegram bot interface using aiogram 3, including FSM flows for wallet binding and cheque creation, async Redis storage, and RU+EN internationalization with wallet-viewkey safety copy.

## Files Created

### Core Bot Files (`src/xmr_cheque_bot/`)

| File | Description | Lines |
|------|-------------|-------|
| `validators.py` | Input validation for Monero addresses, view keys, amounts | ~275 |
| `i18n.py` | RU+EN internationalization with all UI strings | ~480 |
| `storage.py` | Async Redis storage implementing Storage protocol | ~490 |
| `bot.py` | aiogram 3 router with handlers for /start, /bind, /create, /mycheques, /settings | ~590 |

### Test Files (`tests/`)

| File | Description | Test Cases |
|------|-------------|------------|
| `test_validators.py` | Unit tests for validation functions | 18 test methods |
| `test_i18n.py` | Unit tests for i18n system | 13 test classes |

## File Details

### `validators.py`

Input validation module with no external dependencies:

- **`ValidationError`** — Exception with error codes for i18n
- **`validate_monero_address(address)`** — Validates 95-106 char base58 addresses
- **`validate_view_key(view_key)`** — Validates 64-char hex view keys
- **`validate_amount_rub(amount, ...)`** — Validates RUB amount (100-1,000,000)
- **`validate_cheque_description(desc, ...)`** — Sanitizes and validates description
- **`validate_wallet_filename(filename)`** — Security validation for wallet filenames
- **`is_valid_monero_address(address)`** — Boolean convenience function
- **`is_valid_view_key(view_key)`** — Boolean convenience function

### `i18n.py`

Comprehensive internationalization with RU+EN support:

- **`I18nKeys`** — Dataclass with all translation keys as constants
- **`TRANSLATIONS`** — Dictionary with en/ru translation tables
- **`get_text(key, lang, **kwargs)`** — Get translated text with lambda support
- **`get_status_text(status, lang)`** — Get localized status with emoji
- **`I18n`** — Convenience class for language-aware text retrieval
- **`get_language_from_telegram_code(code)`** — Map Telegram locale to bot language

#### Wallet-Viewkey Safety Copy (M4 Requirement)

Critical security warnings included:
- `WALLET_VIEWKEY_WARNING_TITLE` — Security warning header (🔐)
- `WALLET_VIEWKEY_WARNING_TEXT` — Explains view key capabilities and limits
- `WALLET_VIEWKEY_UNDERSTAND` — "I understand, continue" button
- `WALLET_VIEWKEY_BACKUP_TITLE` — Backup reminder header (📝)
- `WALLET_VIEWKEY_BACKUP_TEXT` — Seed phrase and spend key backup instructions
- `WALLET_VIEWKEY_NEVER_SHARE` — Warning to never share spend key/seed

### `storage.py`

Async Redis storage implementing the `Storage` protocol from `payment_monitor`:

- **`StorageError`** — Storage operation exception
- **`RedisStorage`** — Main storage class

#### User Methods
- `get_user(user_id)` — Get UserRecord by ID
- `save_user(user)` — Save user record
- `get_or_create_user(user_id, language)` — Get or create with defaults
- `update_user_activity(user_id)` — Update last activity timestamp

#### Wallet Methods
- `get_wallet(user_id)` — Get UserWallet
- `has_wallet(user_id)` — Check if wallet exists
- `bind_wallet(user_id, address, view_key, ...)` — Encrypt and store wallet
- `unbind_wallet(user_id)` — Remove wallet binding
- `decrypt_view_key(wallet)` — Decrypt view key from wallet
- `check_wallet_bind_rate_limit(user_id)` — Check rate limit

#### Cheque Methods
- `create_cheque(...)` — Create new cheque with indices
- `get_cheque(cheque_id)` — Get cheque by ID
- `save_cheque(cheque)` — Save with TTL based on status
- `cancel_cheque(cheque_id)` — Cancel pending cheque
- `list_user_cheques(user_id, ...)` — List user's cheques
- `count_user_cheques(user_id)` — Count total cheques
- `count_active_cheques(user_id)` — Count non-final cheques

#### Storage Protocol (for payment_monitor)
- `list_pending_cheque_ids()` — Returns IDs from sorted set (score=expires_at)
- `load_cheques(cheque_ids)` — Batch load cheques
- `load_user_wallet(user_id)` — Required by monitor
- `remove_from_pending(cheque_id)` — Remove from pending ZSET

#### Rate Limiting
- `check_cheque_rate_limit(user_id)` — Check creation rate limit

#### Data Deletion
- `delete_all_user_data(user_id)` — GDPR-style full deletion (wallet, cheques, indices, user record)

### `bot.py`

aiogram 3 bot implementation with FSM:

#### FSM States
- **`BindWalletStates`** — safety_warning → enter_address → confirm_address → enter_view_key → confirm_binding
- **`CreateChequeStates`** — enter_amount → enter_description → confirm_cheque
- **`DeleteDataStates`** — confirm_deletion

#### Command Handlers
- `/start` — Welcome, language selection
- `/bind` — Wallet binding flow with safety warnings
- `/create` — Cheque creation flow
- `/mycheques` — List recent cheques
- `/settings` — Settings menu (language, delete data)

#### Key Features
- Language selection with inline buttons
- View key safety warnings before binding (backup reminder + security notice)
- Amount computation with rate fetching
- QR code generation for cheques
- Full data deletion workflow with confirmation

#### Bot Setup Functions
- `create_bot(token)` — Create Bot instance
- `create_dispatcher(storage)` — Create Dispatcher with router
- `setup_bot()` — Full setup with settings

## Test Coverage

### Running Tests

```bash
cd /root/.openclaw/workspace/xmr-cheque-bot
source .venv/bin/activate
pytest tests/test_validators.py tests/test_i18n.py -v
```

### Test Files Summary

**`test_validators.py`** — 18 test methods covering:
- Valid/invalid Monero address validation
- View key format validation (64 hex chars)
- RUB amount validation (bounds, types, formatting)
- Description sanitization
- Wallet filename security (path traversal prevention)
- Convenience boolean functions

**`test_i18n.py`** — 13 test classes covering:
- Key uniqueness and existence
- EN/RU text retrieval
- Lambda translations with kwargs
- Status text localization
- `I18n` class convenience methods
- Language code mapping from Telegram
- **Wallet-viewkey safety copy** verification in both languages
- All critical keys have translations

## Dependencies Used

From existing modules (as per constraints):
- `config` — Settings management
- `encryption` — Fernet encryption for view keys
- `redis_schema` — Data models and key patterns
- `amount` — `compute_cheque_amount()` for XMR conversion
- `uri_qr` — `generate_payment_qr()` for QR codes
- `rates` — Exchange rate fetching (via `amount`)

New dependencies (aiogram 3):
- `aiogram>=3.0.0` — Bot framework
- `redis>=5.0.0` — Async Redis client

## Security Features

1. **View Key Encryption** — All view keys encrypted with Fernet before Redis storage
2. **Path Traversal Prevention** — Wallet filenames validated against traversal patterns
3. **Rate Limiting** — Per-user rate limits for wallet binding and cheque creation
4. **Safety Warnings** — Multi-step warnings before collecting view keys
5. **Input Validation** — Strict validation on addresses, keys, amounts
6. **Data Deletion** — Complete user data removal capability

## Integration Points

### With Payment Monitor

`RedisStorage` implements the `Storage` protocol:
```python
from xmr_cheque_bot.payment_monitor import PaymentMonitor
from xmr_cheque_bot.storage import RedisStorage

storage = RedisStorage()
monitor = PaymentMonitor(storage=storage, rpc=rpc_client)
```

### With Notifier (Future)

The bot can implement the `Notifier` protocol to receive payment updates:
```python
class TelegramNotifier:
    async def notify(self, user_id: str, message_key: str, payload: dict) -> None:
        # Send message via bot
        pass
```

## Next Steps (M5+)

- Connect bot to payment monitor with async task runner
- Implement webhook/long-polling for production
- Add cheque detail view and cancellation inline buttons
- Implement wallet file cleanup on deletion
- Add transaction history export
