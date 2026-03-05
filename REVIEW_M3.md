# M3 Review — XMR Cheque Bot (payment monitor worker)

**Status: PASS**

## Scope (M3)
- Monitor loop (implemented as `run_once()` + optional `run_forever()`)
- Grouping by user, wallet switching via monero-wallet-rpc
- Exact atomic match + min_height filtering
- Status transitions to final at >= confirmations_final (default 6)
- No Telegram handlers (Notifier protocol)
- Unit tests without external services

## Landed artifacts
- `src/xmr_cheque_bot/payment_monitor.py`
- `tests/test_payment_monitor.py`
- `ARTIFACTS_M3.md`

## Important correctness fix included
- `monero_rpc.get_transfers()` now sets `filter_by_height=true` when min/max height is provided.

## Verification
- `. .venv/bin/activate && python -m pytest -q` → PASS

## Notes
- For production, add a real Redis-backed Storage implementation (async redis client) and integrate with bot layer.
- Next milestone M4: Telegram handlers + RU/EN i18n + menus + pagination + settings.
