# M1 Review — XMR Cheque Bot (core: RPC + schema + encryption)

**Status: PASS**

## Scope (M1)
- Async client for `monero-wallet-rpc`
- Redis schema/key helpers + TTL rules
- Fernet encryption helpers
- Unit tests (no external services)

## What landed in repo
- `src/xmr_cheque_bot/monero_rpc.py`
- `src/xmr_cheque_bot/redis_schema.py`
- `src/xmr_cheque_bot/encryption.py`
- `tests/test_encryption.py`, `tests/test_redis_schema.py`
- `pytest.ini` (pythonpath=src)
- `ARTIFACTS_M1.md`

## Verification
- `python3 -m pytest -q` → PASS

## Notes
- `create_encryption_manager()` reads `VIEW_KEY_ENCRYPTION_KEY` directly to avoid requiring full Settings during unit tests.
- Next milestone (M2): cheque creation (rate fetch + atomic math + unique tail + URI/QR) + limits.
