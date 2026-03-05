# REVIEW — Mainnet deploy prep

Status: PASS

## Reviewer checklist
- [x] No secrets committed (`.env` remains gitignored; no token values added)
- [x] `.env.example` contains required compose variables (`WALLET_RPC_USER/PASS`, `BOT_TOKEN`, `VIEW_KEY_ENCRYPTION_KEY`)
- [x] Mainnet override file exists and fully overrides stagenet-specific flags/ports
- [x] Healthchecks updated for mainnet ports in override
- [x] Compose parses with override (`docker compose ... config`)

## Notes
- Mainnet sync will take time/disk; `--prune-blockchain` is enabled.
