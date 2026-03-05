# M4 Review — XMR Cheque Bot (Telegram bot layer)

**Status: PASS**

## Scope (M4)
- aiogram 3 bot entry/router + basic flows
- RU+EN i18n
- Validators for address/view key/amount/description
- Redis-backed storage layer (async) with decode_responses
- Delete-data path (wipe user data) scaffolding
- Unit tests for validators + i18n (no external services)

## Artifacts present
- `src/xmr_cheque_bot/bot.py`
- `src/xmr_cheque_bot/storage.py`
- `src/xmr_cheque_bot/i18n.py`
- `src/xmr_cheque_bot/validators.py`
- `tests/test_validators.py`
- `tests/test_i18n.py`
- `ARTIFACTS_M4.md`

## Verification
- `. .venv/bin/activate && python -m pytest -q` → PASS

## Notes
- Next milestone M5: wire everything together for staging run (compose env, bot start command, monitor start, stagenet smoke test), then hardening + ops.
