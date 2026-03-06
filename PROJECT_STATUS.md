# Project Status — xmr-cheque-bot

Stage: **CI → E2E → SHIP**

## Links
- Repo: https://github.com/Pugg213/xmr-cheque-bot
- Latest prod-ready hardening commit: `87cf65aada7a884ff808a702344e185f259aec18`

## Gates (Definition of Done)

### P0 closed ✅
- Wallet password applied at wallet creation (generate_from_keys uses same password stored in Redis)
- `min_height` uses real chain height (with reorg buffer)
- Compose hardening: internal service network for redis + wallet-rpc + app; no published ports

### CI green ⏳
- GitHub Actions on `main` passes (ruff + tests). Mypy is non-blocking for MVP.

### E2E ⏳
Minimal stagenet E2E scenario:
1) Bring up stack: `docker compose -f docker-compose.yml up -d --build`
2) Bind test wallet (address + view key)
3) Create cheque
4) Send exact amount on stagenet
5) Observe transition: PENDING → MEMPOOL → CONFIRMING → CONFIRMED

Artifacts to capture:
- docker logs for monitor (showing detection + confirmations)
- screenshot/log line confirming CONFIRMED

### SHIP (mainnet) ⏳
1) Deploy on server
2) Provide `.env` (BOT_TOKEN, VIEW_KEY_ENCRYPTION_KEY, WALLET_RPC_USER/PASS, optional COINGECKO_API_KEY)
3) Start:
   - `docker compose -f docker-compose.yml -f docker-compose.mainnet.yml -f docker-compose.production.yml up -d --build`
4) Health checks:
   - `docker ps`
   - monerod sync progressing
   - wallet-rpc healthy
   - app logs ok

Rollback:
- `git reset --hard <previous_commit>` + `docker compose up -d --build`
