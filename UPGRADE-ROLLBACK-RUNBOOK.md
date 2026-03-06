# Upgrade & Rollback Runbook — XMR Cheque Bot

This runbook covers standard operational procedures for the XMR Cheque Bot production deployment.

## Quick Reference

| Action | Command/Link |
|--------|--------------|
| Check status | `docker compose ps` |
| View logs | `docker compose logs -f` |
| Health check | `./scripts/health-check.sh` |
| Emergency stop | `docker compose down` |
| Rollback | See [Rollback Procedure](#rollback-procedure) |

## Services Overview

```
Production deployment:
├── monerod              # Monero daemon (mainnet, pruned)
├── monero-wallet-rpc    # Wallet RPC service
├── redis                # State persistence
├── app-bot              # Telegram bot (polling)
└── app-monitor          # Payment monitor worker
```

All services defined via:
- `docker-compose.yml` (base)
- `docker-compose.mainnet.yml` (mainnet config)
- `docker-compose.production.yml` (production settings)

## Standard Operations

### Daily Operations

#### Check Service Health
```bash
cd /opt/xmr-cheque-bot

# Container status
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  ps

# Resource usage
docker stats --no-stream

# Quick health check
./scripts/health-check.sh
```

#### View Logs
```bash
cd /opt/xmr-cheque-bot

# All services
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  logs -f

# Specific service
docker logs -f xmr-bot-app-bot
docker logs -f xmr-bot-app-monitor
docker logs -f xmr-bot-monerod

# Last 100 lines with timestamps
docker logs --tail 100 -t xmr-bot-app-bot
```

#### Check Sync Status
```bash
# monerod sync status
curl -s http://localhost:18081/get_info | jq .

# Height comparison
curl -s http://localhost:18081/get_info | jq '{height: .height, target: .target_height, sync: .synchronized}'
```

### Weekly Operations

#### Verify Backups
```bash
# Check backup files exist
ls -la /opt/xmr-cheque-bot/backups/

# Check backup integrity
 tar -tzf /opt/xmr-cheque-bot/backups/wallets_$(date +%Y%m%d)*.tar.gz > /dev/null && echo "Wallet backup OK"

# Check backup age
find /opt/xmr-cheque-bot/backups/ -name "*.tar.gz" -mtime -1 | wc -l
```

#### Update System Packages
```bash
# Update OS packages (safe to do regularly)
sudo apt update
sudo apt upgrade -y

# Review if Docker update needed
sudo apt list --upgradable | grep docker
```

### Monthly Operations

#### Review Resource Usage
```bash
# Disk usage
df -h

# Container disk usage
docker system df

# Clean up unused images (caution)
docker image prune -a --filter "until=720h"

# Review logs for errors
docker logs xmr-bot-app-bot --since 720h 2>&1 | grep -i error | wc -l
```

## Upgrade Procedures

### Type 1: Application Code Update (New Version)

**Risk Level:** Low-Medium  
**Downtime:** ~30 seconds  
**Pre-req:** Working backup

```bash
cd /opt/xmr-cheque-bot

# 1. Pre-upgrade backup
./scripts/backup.sh

# 2. Record current version
git rev-parse HEAD > /tmp/pre-upgrade-commit.txt

# 3. Pull latest code
git fetch origin
git log --oneline HEAD..origin/main  # Review changes
git pull origin main

# 4. Rolling restart (bot first to avoid stuck payments)
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d --build --no-deps app-bot

# 5. Wait for bot to be healthy (check logs)
sleep 5
docker logs xmr-bot-app-bot --tail 20

# 6. Restart monitor
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d --build --no-deps app-monitor

# 7. Verify all healthy
docker compose ps
```

### Type 2: Docker Image Updates

**Risk Level:** Low  
**Downtime:** Minimal (rolling restart)

```bash
cd /opt/xmr-cheque-bot

# Backup before updates
./scripts/backup.sh

# Pull new images
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  pull

# Restart services (order matters)
# 1. Redis (state preserved)
docker compose restart redis

# 2. App services
docker compose restart app-bot app-monitor

# 3. Wallet RPC (depends on monerod)
docker compose restart monero-wallet-rpc

# 4. monerod last (avoid unnecessary re-sync)
docker compose restart monerod
```

### Type 3: Monerod Upgrade (Hard Fork)

**Risk Level:** High  
**Downtime:** Minutes to hours  
**Pre-req:** Follow Monero official announcements

```bash
cd /opt/xmr-cheque-bot

# 1. Read official upgrade notes
# https://github.com/monero-project/monero/releases

# 2. Full backup (critical!)
./scripts/backup.sh

# 3. Stop app services first (graceful shutdown)
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  stop app-bot app-monitor

# 4. Stop wallet-rpc
docker compose stop monero-wallet-rpc

# 5. Stop monerod
docker compose stop monerod

# 6. Pull latest monerod image
docker pull ghcr.io/sethforprivacy/simple-monerod:latest

# 7. Start monerod (may have DB migration)
docker compose start monerod
docker logs -f xmr-bot-monerod  # Watch for errors

# 8. Wait for monerod to be responsive
sleep 30
curl -s http://localhost:18081/get_height

# 9. Pull and start wallet-rpc
docker pull ghcr.io/sethforprivacy/simple-monero-wallet-rpc:latest
docker compose start monero-wallet-rpc

# 10. Start app services
docker compose start app-bot app-monitor

# 11. Full status check
docker compose ps
```

### Type 4: Configuration Changes

**Risk Level:** Low  
**Downtime:** Minimal

```bash
cd /opt/xmr-cheque-bot

# 1. Edit .env
nano .env

# 2. Validate syntax
source .env && echo "Syntax OK"

# 3. Restart affected services
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d
```

## Rollback Procedure

### Scenario 1: Rollback Application Code

**Use when:** New deployment has bugs

```bash
cd /opt/xmr-cheque-bot

# 1. Stop app services
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  stop app-bot app-monitor

# 2. Restore previous commit
git log --oneline -5  # Find working commit
git checkout <working-commit-hash>

# 3. Rebuild and start
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d --build app-bot app-monitor

# 4. Verify
docker compose ps
docker logs xmr-bot-app-bot --tail 20
```

### Scenario 2: Rollback Data (Corruption)

**Use when:** Data corruption, wallet issues

```bash
cd /opt/xmr-cheque-bot

# 1. EMERGENCY STOP
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  down

# 2. Identify backup to restore
ls -la /opt/xmr-cheque-bot/backups/
# Choose: wallets_YYYYMMDD_HHMMSS.tar.gz and redis_YYYYMMDD_HHMMSS.tar.gz

# 3. Restore wallet files
sudo bash -c '
  cd /opt/xmr-cheque-bot/backups
  docker run --rm -v xmr-cheque-bot_wallet_files:/wallet -v "$PWD:/backup" alpine \
    tar xzf /backup/wallets_YYYYMMDD_HHMMSS.tar.gz -C /wallet
'

# 4. Restore Redis data (optional - only if Redis corrupted)
sudo bash -c '
  cd /opt/xmr-cheque-bot/backups
  docker run --rm -v xmr-cheque-bot_redis_data:/data -v "$PWD:/backup" alpine \
    tar xzf /backup/redis_YYYYMMDD_HHMMSS.tar.gz -C /data
'

# 5. Start services
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d

# 6. Verify logs
docker logs xmr-bot-monerod --tail 50
docker logs xmr-bot-app-bot --tail 20
```

### Scenario 3: Complete Disaster Recovery

**Use when:** Total VPS failure, migrating to new server

```bash
# ON NEW SERVER:

# 1. Follow PROVISIONING-CHECKLIST.md up to Phase 3

# 2. Copy backup files from secure storage
mkdir -p /opt/xmr-cheque-bot/backups
# Copy wallets_*.tar.gz and redis_*.tar.gz from backup storage

# 3. Restore data BEFORE first start
cd /opt/xmr-cheque-bot

# Create empty volumes first
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d redis monerod

docker compose stop redis monerod

# Restore wallet files
docker run --rm -v xmr-cheque-bot_wallet_files:/wallet \
  -v /opt/xmr-cheque-bot/backups:/backup alpine \
  tar xzf /backup/wallets_YYYYMMDD_HHMMSS.tar.gz -C /wallet

# Restore Redis data
docker run --rm -v xmr-cheque-bot_redis_data:/data \
  -v /opt/xmr-cheque-bot/backups:/backup alpine \
  tar xzf /backup/redis_YYYYMMDD_HHMMSS.tar.gz -C /data

# 4. Start full stack
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d

# 5. Verify
docker compose ps
./scripts/health-check.sh
```

## Troubleshooting

### monerod Not Syncing

```bash
# Check logs
docker logs xmr-bot-monerod --tail 100

# Check network connectivity
docker exec xmr-bot-monerod curl -s http://localhost:18081/get_info

# Restart if stuck
docker restart xmr-bot-monerod
```

### Wallet RPC Connection Failed

```bash
# Check if wallet-rpc is running
docker ps | grep wallet-rpc

# Check logs
docker logs xmr-bot-wallet-rpc

# Test RPC manually
curl -u "$WALLET_RPC_USER:$WALLET_RPC_PASS" \
  http://localhost:18083/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_version"}' \
  -H 'Content-Type: application/json'
```

### Bot Not Responding

```bash
# Check if bot is running
docker ps | grep app-bot

# Check logs for errors
docker logs xmr-bot-app-bot --tail 50

# Verify Telegram token
docker exec xmr-bot-app-bot env | grep BOT_TOKEN

# Restart
docker restart xmr-bot-app-bot
```

### Monitor Missing Payments

```bash
# Check monitor logs
docker logs xmr-bot-app-monitor --tail 100

# Check Redis connection
docker exec xmr-bot-app-monitor redis-cli -h redis ping

# Restart
docker restart xmr-bot-app-monitor
```

### Disk Full

```bash
# Check disk usage
df -h

# Check Docker usage
docker system df

# Clean up
# 1. Remove old backups (keep last 7 days)
find /opt/xmr-cheque-bot/backups/ -name "*.tar.gz" -mtime +7 -delete

# 2. Prune Docker
docker system prune -a --volumes

# 3. Check monerod pruning is enabled
docker logs xmr-bot-monerod | grep -i prune
```

## Emergency Contacts & Resources

| Resource | URL |
|----------|-----|
| Monero Releases | https://github.com/monero-project/monero/releases |
| Docker Docs | https://docs.docker.com/compose/ |
| Telegram Bot API | https://core.telegram.org/bots/api |
| Repository | https://github.com/Pugg213/xmr-cheque-bot |

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-03-06 | Initial runbook | ops-agent |
