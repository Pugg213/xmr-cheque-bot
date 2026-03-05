# ARTIFACTS M3 — Payment Monitor

## Added
- `src/xmr_cheque_bot/payment_monitor.py`
  - `PaymentMonitor.run_once()` processes pending cheques
  - exact amount match + min_height rule
  - global RPC lock + per-user lock
  - status transitions to final at 6 confirmations
  - notification via `Notifier` protocol (no Telegram handlers)

- `tests/test_payment_monitor.py`
  - matching rules
  - status mapping
  - monitor run_once behavior with in-memory storage + fake RPC

## How to run tests
```bash
cd xmr-cheque-bot
. .venv/bin/activate
python -m pytest -q
```
