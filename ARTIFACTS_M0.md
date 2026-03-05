# Milestone M0 — Handoff Note

**Date:** 2026-03-05  
**Status:** ✅ Complete (Project Skeleton)

## What Was Created

### 1. Docker Compose Infrastructure (`docker-compose.yml`)

Four services configured for stagenet:

| Service | Image/Build | Purpose | Named Volume |
|---------|-------------|---------|--------------|
| `redis` | `redis:7-alpine` | State storage | `redis_data` |
| `monerod` | `ghcr.io/sethforprivacy/simple-monerod` | Monero daemon (stagenet) | `monero_data` |
| `monero-wallet-rpc` | `ghcr.io/sethforprivacy/simple-monero-wallet-rpc` | Wallet RPC | `wallet_files` |
| `app` | Build from `Dockerfile` | Telegram bot | — (readonly mount of `wallet_files`) |

Key features:
- All services on internal network `xmr-bot-net`
- Health checks configured
- Proper startup dependencies (`depends_on` with conditions)
- Named volumes for persistence across restarts

### 2. Python App Skeleton (`src/xmr_cheque_bot/`)

```
src/xmr_cheque_bot/
├── __init__.py       # Package init with version
├── __main__.py       # Entry point (async main loop)
├── config.py         # Pydantic-settings configuration
└── logging.py        # Structured logging with structlog
```

**`config.py`:**
- Settings loaded from environment variables
- Validation for encryption key format (Fernet base64)
- Defaults for stagenet URLs
- All configurable parameters defined (MVP spec compliant)

**`logging.py`:**
- JSON structured logging via structlog
- Secret masking utilities (`mask_sensitive()`)
- Log level configurable via `LOG_LEVEL` env var

### 3. Project Configuration

- **`pyproject.toml`**: Modern Python packaging, dependencies, dev tools (ruff, mypy, pytest)
- **`Dockerfile`**: Multi-stage build, non-root user, proper layer caching
- **`.env.example`**: Template with all required/suggested variables
- **`.gitignore`**: Comprehensive ignore patterns (secrets, Python artifacts, wallet files)

### 4. Documentation

- **`README.md`**: Setup instructions, stagenet guide, development info

## How to Run (Stagenet)

```bash
# 1. Navigate to project
cd xmr-cheque-bot

# 2. Create .env from template
cp .env.example .env

# 3. Edit .env with your values:
#   BOT_TOKEN=your_telegram_bot_token
#   VIEW_KEY_ENCRYPTION_KEY=your_fernet_key  # generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. Start infrastructure
docker compose up -d

# 5. Check logs
docker compose logs -f app

# 6. Verify services are healthy
docker compose ps
```

## What is NOT Included (M1-M4)

As per M0 scope, the following is NOT implemented:

- ❌ Monero RPC client
- ❌ Wallet manager (create/open/delete view-only wallets)
- ❌ Redis schema (user/cheque records)
- ❌ Encryption helpers for view keys
- ❌ Telegram bot handlers
- ❌ Cheque creation logic
- ❌ Payment monitor worker
- ❌ Rate limiting
- ❌ QR code generation

These are scheduled for M1-M4 as per `DEV_TASKLIST_v1.1.md`.

## Next Steps for M1

1. **Async Monero RPC client** in `src/xmr_cheque_bot/rpc.py`
2. **Wallet manager** in `src/xmr_cheque_bot/wallet.py`
3. **Redis schema** with proper key naming conventions
4. **Encryption helpers** using Fernet

## Security Notes

- Wallet files stored in `wallet_files` named volume (persisted, not in git)
- Encryption key validated to be 32-byte base64 (Fernet format)
- `.env` and secrets excluded from git via `.gitignore`
- App container mounts wallet_files as read-only (writes done via wallet-rpc)

## Files Summary

```
xmr-cheque-bot/
├── docker-compose.yml      # Infrastructure orchestration
├── Dockerfile              # App container build
├── pyproject.toml          # Python dependencies & tooling
├── .env.example            # Env template (no secrets)
├── .gitignore              # Prevents secret leaks
├── README.md               # Setup & usage guide
├── src/
│   └── xmr_cheque_bot/
│       ├── __init__.py
│       ├── __main__.py     # Entry point
│       ├── config.py       # Settings (pydantic-settings)
│       └── logging.py      # Structured logging
└── ARTIFACTS_M0.md         # This file
```

---
**M0 Complete** — Ready for M1 implementation.