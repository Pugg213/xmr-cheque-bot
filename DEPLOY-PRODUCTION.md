# XMR Cheque Bot — Production Deployment Summary

This directory contains complete production deployment artifacts for the XMR Cheque Bot.

## Quick Start

```bash
# 1. Provision VPS using PROVISIONING-CHECKLIST.md
# 2. Deploy application

ssh xmrbot@your-vps-ip
cd /opt/xmr-cheque-bot

# Validate configuration
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml -f docker-compose.production.yml config

# Start all services
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml -f docker-compose.production.yml up -d

# Check status
./scripts/health-check.sh
```

## File Structure

```
/opt/xmr-cheque-bot/
├── docker-compose.yml                 # Base services (stagenet defaults)
├── docker-compose.mainnet.yml         # Mainnet network configuration
├── docker-compose.production.yml      # Production overrides (resources, scaling)
│
├── OPS-PRODUCTION-DEPLOY.md           # Architecture documentation
├── PROVISIONING-CHECKLIST.md          # Step-by-step VPS setup
├── UPGRADE-ROLLBACK-RUNBOOK.md        # Operational procedures
│
├── scripts/
│   ├── backup.sh                      # Automated backup script
│   └── health-check.sh                # Health verification
│
├── monitoring/
│   ├── prometheus.yml                 # Prometheus configuration
│   └── alert-rules.yml                # Alerting rules
│
├── systemd/
│   └── xmr-cheque-bot.service         # systemd service unit
│
├── backups/                           # Backup storage (created by backup script)
└── .env                               # Secrets (not in git)
```

## Architecture Overview

### Services

| Service | Purpose | Scaling |
|---------|---------|---------|
| `monerod` | Monero blockchain daemon | Single instance only |
| `monero-wallet-rpc` | Wallet RPC interface | Single instance only |
| `redis` | State persistence | Single instance (can use Redis Sentinel for HA) |
| `app-bot` | Telegram bot (polling) | 1 replica (Telegram limitation) |
| `app-monitor` | Payment monitor worker | 1+ replicas (horizontal scaling) |

### Scaling Options

**Option A: Single Server (Default)**
```bash
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d
```

**Option B: Separate Bot + Monitor**
```bash
# Bot only
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d app-bot

# Multiple monitors
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d --scale app-monitor=3 app-monitor
```

**Option C: Webhook Mode (Future)**
- Requires HTTPS endpoint
- Enables horizontal bot scaling
- See architecture docs for details

## Security Checklist

- [ ] `.env` file has permissions 0600
- [ ] Firewall (UFW) enabled, only ports 22 and 18080 open
- [ ] SSH key authentication only (no password)
- [ ] Root login disabled
- [ ] fail2ban enabled
- [ ] Docker daemon secured
- [ ] Regular backups configured (cron)
- [ ] Log rotation enabled
- [ ] No secrets in environment dumps

## Monitoring

### Basic (Logs)
```bash
docker compose logs -f
./scripts/health-check.sh
```

### Advanced (Prometheus + Grafana)
Uncomment monitoring services in `docker-compose.production.yml`:
```yaml
services:
  prometheus:
    # ...
  grafana:
    # ...
```

Access Grafana via SSH tunnel:
```bash
ssh -L 3000:localhost:3000 xmrbot@your-vps-ip
# Open http://localhost:3000 in browser
```

## Backup & Recovery

### Automated Backups
Daily backups run via cron (configured in PROVISIONING-CHECKLIST.md):
- Wallet files: `/opt/xmr-cheque-bot/backups/wallets_*.tar.gz`
- Redis data: `/opt/xmr-cheque-bot/backups/redis_*.tar.gz`
- Retention: 7 days

### Manual Backup
```bash
./scripts/backup.sh
```

### Restore
See UPGRADE-ROLLBACK-RUNBOOK.md for complete restore procedures.

## Common Operations

| Task | Command |
|------|---------|
| Check status | `docker compose ps` |
| View logs | `docker compose logs -f [service]` |
| Restart | `docker compose restart [service]` |
| Scale monitors | `docker compose up -d --scale app-monitor=N app-monitor` |
| Update images | `docker compose pull && docker compose up -d` |
| Health check | `./scripts/health-check.sh` |

## Troubleshooting

See UPGRADE-ROLLBACK-RUNBOOK.md for detailed troubleshooting procedures.

Quick checks:
```bash
# All services running?
docker compose ps

# monerod synced?
curl -s http://localhost:18081/get_info | jq '.synchronized,.height,.target_height'

# Bot responsive?
docker logs xmr-bot-app-bot --tail 20

# Resources?
docker stats --no-stream
```

## Production Checklist

Before declaring production-ready:

- [ ] VPS provisioned per PROVISIONING-CHECKLIST.md
- [ ] Environment configured in `.env`
- [ ] Backup script tested and working
- [ ] monerod fully synced
- [ ] Bot responding to Telegram commands
- [ ] Test payment flow completed
- [ ] Monitoring configured
- [ ] Team trained on runbook
- [ ] Emergency contacts documented

## Support

- **Documentation**: See OPS-PRODUCTION-DEPLOY.md, PROVISIONING-CHECKLIST.md, UPGRADE-ROLLBACK-RUNBOOK.md
- **Issues**: https://github.com/Pugg213/xmr-cheque-bot/issues
- **Monero Docs**: https://monerodocs.org/
