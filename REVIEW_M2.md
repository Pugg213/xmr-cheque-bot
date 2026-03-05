# M2 Review — XMR Cheque Bot (cheque creation utilities)

**Status: PASS**

## Scope (M2)
- Fetch XMR/RUB rate (CoinGecko) with cache
- RUB→atomic math with Decimal + unique tail 1..9999 piconero
- Monero URI + QR generation (PNG bytes)
- Max active cheques per user = 10 (function-level gate)
- Unit tests

## Landed files
- `src/xmr_cheque_bot/rates.py`
- `src/xmr_cheque_bot/amount.py`
- `src/xmr_cheque_bot/uri_qr.py`
- `src/xmr_cheque_bot/cheque_limits.py`
- `tests/test_cheque_creation.py`
- `ARTIFACTS_M2.md`

## Verification
- In repo venv: `. .venv/bin/activate && python -m pytest -q` → PASS

## Notes
- Keep using Decimal end-to-end; never derive display from float.
- Next milestone M3: payment monitor worker + per-user wallet locking + status transitions to 6 confirmations.
