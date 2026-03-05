# Milestone M1 — Artifacts and Documentation

**Status:** ✅ Complete  
**Scope:** Core RPC + Storage + Encryption  
**Date:** 2026-03-05

---

## File List

### Source Code (`src/xmr_cheque/`)

| File | Description |
|------|-------------|
| `__init__.py` | Package initialization with version |
| `config.py` | Pydantic settings (env vars, defaults) |
| `encryption.py` | Fernet encryption for view keys and passwords |
| `monero_rpc.py` | Async Monero wallet RPC client (httpx) |
| `redis_schema.py` | Redis keys, dataclasses, TTL helpers |

### Tests (`tests/`)

| File | Description |
|------|-------------|
| `test_encryption.py` | Unit tests for EncryptionManager |
| `test_redis_schema.py` | Unit tests for schema dataclasses |

### Configuration

| File | Description |
|------|-------------|
| `pyproject.toml` | Project metadata, dependencies, tool config |
| `pytest.ini` | Pytest configuration |

---

## Implementation Details

### 1. Async Monero Wallet RPC Client (`monero_rpc.py`)

**Methods implemented:**
- `generate_from_keys()` — Create view-only wallet from address + view key
- `open_wallet()` — Open existing wallet file
- `close_wallet()` — Close wallet with optional autosave
- `refresh()` — Scan for new transactions
- `get_transfers()` — Query transfers with filters
- `get_version()` — RPC version info

**Additional convenience methods:**
- `get_incoming_transfers()` — Filtered incoming + mempool for monitoring
- `get_current_height()` — Current blockchain height
- `check_health()` — RPC health check

**Features:**
- HTTP Basic Auth support
- Configurable timeouts
- Context manager (`async with`)
- Proper error handling with `MoneroRPCError`

### 2. Redis Schema (`redis_schema.py`)

**Key Patterns (`RedisKeys`):**
```python
user:{user_id}                    # User profile
user:{user_id}:wallet             # Wallet binding
user_cheques:{user_id}            # User's cheque index (sorted set)
cheque:{cheque_id}                # Cheque record
pending_cheques                   # Global pending index
ratelimit:cheque:{user_id}        # Rate limit tracking
ratelimit:wallet_bind:{user_id}
```

**Dataclasses:**
- `UserRecord` — User profile, language preference
- `UserWallet` — Encrypted view key, wallet file reference
- `ChequeRecord` — Core cheque with amount_atomic_expected, min_height, status, timestamps

**ChequeStatus enum:**
- `pending` — Created, no tx found
- `mempool` — Tx found in mempool (0 conf)
- `confirming` — 1..5 confirmations
- `confirmed` — >=6 confirmations (final)
- `expired` — TTL exceeded
- `cancelled` — User cancelled

**TTL Helpers:**
- `TTLConfig` — Configurable TTL values
- `get_cheque_ttl()` — Status-based TTL calculation

### 3. Encryption Module (`encryption.py`)

**Features:**
- Fernet symmetric encryption (cryptography library)
- Automatic key generation
- Encrypt/decrypt with authenticated encryption
- `create_encryption_manager()` factory from settings

**Usage:**
```python
from xmr_cheque.encryption import EncryptionManager

key = EncryptionManager.generate_key()  # Store securely
manager = EncryptionManager(key)

ciphertext = manager.encrypt(view_key)
plaintext = manager.decrypt(ciphertext)
```

---

## How to Run Tests

### Prerequisites

```bash
cd /root/.openclaw/workspace/xmr-cheque
pip install -e ".[dev]"
```

### Run All Tests

```bash
pytest -v
```

### Run Specific Test Files

```bash
pytest tests/test_encryption.py -v
pytest tests/test_redis_schema.py -v
```

### Run with Coverage

```bash
pytest --cov=src/xmr_cheque --cov-report=term-missing
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `XMR_REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `XMR_MONERO_RPC_URL` | `http://localhost:18082/json_rpc` | Wallet RPC endpoint |
| `XMR_MONERO_RPC_USERNAME` | — | RPC auth username |
| `XMR_MONERO_RPC_PASSWORD` | — | RPC auth password |
| `XMR_VIEW_KEY_ENCRYPTION_KEY` | — | Fernet key for encryption |
| `XMR_CHEQUE_TTL_SECONDS` | `3600` | Cheque validity |
| `XMR_MAX_ACTIVE_CHEQUES_PER_USER` | `10` | Max active cheques |

---

## Constraints Followed

✅ **No Telegram bot flows** — No bot/telegram imports  
✅ **No cheque creation logic** — Schema only, no business logic  
✅ **No external network calls in tests** — Pure unit tests  
✅ **No Monero node required** — RPC client tested via mocking in future milestones  

---

## Next Milestones

- **M2:** Cheque creation (rate fetch, unique tail, QR/URI generation)
- **M3:** Payment monitor worker (loop, matching algorithm, confirmations)
- **M4:** Telegram bot flows (RU+EN)
- **M5:** Privacy & retention rules
