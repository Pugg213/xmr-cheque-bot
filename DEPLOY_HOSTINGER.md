# Deploy on Hostinger VPS (Docker Compose)

This project ships with a default **stagenet** compose (`docker-compose.yml`) and a **mainnet override** (`docker-compose.mainnet.yml`).

## Prereqs
- Ubuntu VPS with Docker + Compose plugin installed.
- A dedicated Telegram bot token for this bot (do **not** reuse your OpenClaw bot token).

## 1) Clone
```bash
git clone https://github.com/Pugg213/xmr-cheque-bot.git
cd xmr-cheque-bot
```

## 2) Create `.env`
```bash
cp .env.example .env
nano .env
```

Fill required vars:
- `BOT_TOKEN` — from @BotFather
- `WALLET_RPC_USER`, `WALLET_RPC_PASS` — HTTP basic auth for `monero-wallet-rpc`
- `VIEW_KEY_ENCRYPTION_KEY` — Fernet key (32 bytes base64). Safe generator (no extra deps):

```bash
python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

## 3) Start (MAINNET)
```bash
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml up -d --build
```

## 4) Observe logs
```bash
docker compose logs -f monerod
# in another terminal
docker compose logs -f monero-wallet-rpc
# and the app
docker compose logs -f app
```

## Notes
- No host ports are published by default. The bot uses Telegram polling, so inbound HTTP is not required.
- `monerod` will sync from scratch (mainnet). Expect disk + time usage. Consider pruning (`--prune-blockchain` is enabled).
- Wallet files are stored in the named volume `wallet_files`.
- Never commit `.env`.
