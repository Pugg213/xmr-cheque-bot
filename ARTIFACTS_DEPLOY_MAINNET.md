# ARTIFACTS — Mainnet deploy prep

## Goal
Make the repo deployable to **mainnet** on a VPS (Hostinger) without manual edits to the base stagenet compose.

## Changes
- Added `.env.example` entries:
  - `WALLET_RPC_USER`
  - `WALLET_RPC_PASS`
  - clarified `VIEW_KEY_ENCRYPTION_KEY` generation (no extra deps)
- Added `docker-compose.mainnet.yml` override:
  - switches monerod/wallet-rpc to mainnet ports (18080/18081/18083)
  - removes `--stagenet`
  - updates healthchecks accordingly
  - updates app `MONERO_RPC_URL` to port 18083
- Updated `README.md` to recommend override usage.
- Added `DEPLOY_HOSTINGER.md` runbook.

## Checks performed
- `docker compose -f docker-compose.yml -f docker-compose.mainnet.yml config` (parses OK; env warnings expected when unset).
