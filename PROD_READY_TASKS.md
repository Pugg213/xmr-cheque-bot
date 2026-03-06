# PROD-READY Tasklist (XMR Cheque Bot)

Status: draft (assembled by orchestrator). Sources: sec-agent + ops-agent reviews.

## P0 — MUST FIX before any real users / production

### P0-1 Wallet password is not applied to wallet file
- Symptom: wallet is created with empty password but a random password is stored later.
- Risk: wallet files at rest may be unencrypted.
- Fix:
  - Generate `wallet_password` BEFORE `generate_from_keys`.
  - Call `generate_from_keys(... password=wallet_password ...)`.
  - Store encrypted `wallet_password` as already designed.
  - Add migration/repair path for existing wallets.

### P0-2 Broken `min_height` (timestamp used instead of chain height)
- Risk: confirmed transfers ignored by monitor (missed payments).
- Fix:
  - On cheque creation, set `min_height` from RPC chain height (with small reorg buffer).
  - Add end-to-end test: create cheque → pay → confirm → monitor reaches CONFIRMED.

### P0-3 Wallet-RPC / monerod network exposure hardening
- Current compose binds RPC to 0.0.0.0 with `--confirm-external-bind`.
- Fix:
  - Ensure no ports are published.
  - Prefer internal docker network (`internal: true`) and strict service-to-service access.
  - Keep `--rpc-login` mandatory.
  - Document Hostinger firewall expectations.

## P1 — SHOULD FIX for public multi-user robustness

### P1-1 Abuse resistance (Telegram rate limiting)
- Expand rate limits beyond /bind and /create:
  - callbacks per minute
  - pagination / mycheques
  - invalid input attempts
  - new-user cooldown

### P1-2 Redis hardening
- Add Redis auth (`requirepass`) and use authenticated URL.
- Keep AOF, define backup policy.

### P1-3 HTML escaping for user-supplied fields
- Escape description/title when using `parse_mode=HTML`.

### P1-4 Expiry enforcement
- Mark cheques as EXPIRED and define late-payment policy.

## Ops deliverables already prepared (to integrate / review)
- `OPS-PRODUCTION-DEPLOY.md`
- `docker-compose.production.yml`
- `PROVISIONING-CHECKLIST.md`
- `UPGRADE-ROLLBACK-RUNBOOK.md`
- `DEPLOY-PRODUCTION.md`
- `systemd/xmr-cheque-bot.service`
- `monitoring/*` (optional)

## QA deliverables (pending)
- CI pipeline (GitHub Actions)
- Additional test coverage plan (integration/reorg/concurrency)
- Release gates for prod deploy
