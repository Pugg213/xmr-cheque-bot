# Production Deployment Architecture — XMR Cheque Bot

## Overview

Multi-service Docker Compose deployment for production mainnet with:
- **monerod** — Monero daemon (pruned, mainnet)
- **monero-wallet-rpc** — Wallet RPC service
- **redis** — State persistence
- **app-bot** — Telegram bot (scalable horizontally)
- **app-monitor** — Payment monitor worker (scalable horizontally)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         VPS (Cloud)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   monerod   │  │    redis    │  │   monero-wallet-rpc     │  │
│  │  (18080/81) │  │   (6379)    │  │       (18083)           │  │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘  │
│         │                │                     │                │
│         └────────────────┴─────────────────────┘                │
│                          │                                      │
│              ┌───────────┴───────────┐                         │
│              │      Docker Net       │                         │
│              └───────────┬───────────┘                         │
│              ┌───────────┴───────────┐                         │
│              │                       │                         │
│         ┌────┴────┐            ┌────┴────┐                    │
│         │app-bot  │            │app-monitor│                   │
│         │(bot)    │            │(monitor) │                   │
│         └─────────┘            └─────────┘                    │
│              ↑                       ↑                         │
│         Telegram               Blockchain                     │
│         Polling API            Polling RPC                    │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
/opt/xmr-cheque-bot/
├── docker-compose.yml              # Base (stagenet - unchanged)
├── docker-compose.mainnet.yml      # Mainnet overrides
├── docker-compose.production.yml   # Production enhancements
├── docker-compose.override.yml     # Local env overrides (gitignored)
├── .env                            # Secrets (gitignored, 0600)
├── .env.production                 # Production defaults
├── scripts/
│   ├── backup.sh                   # Automated backup script
│   ├── restore.sh                  # Restore from backup
│   └── health-check.sh             # Health check endpoint
├── monitoring/
│   ├── prometheus.yml              # Prometheus config
│   ├── alert-rules.yml             # Alerting rules
│   └── grafana-dashboard.json      # Dashboard import
└── systemd/
    └── xmr-cheque-bot.service      # systemd service unit
```

## Components

### 1. monerod (Monero Daemon)

| Setting | Value | Notes |
|---------|-------|-------|
| Image | `ghcr.io/sethforprivacy/simple-monerod:latest` | Trusted community build |
| Network | mainnet | No `--stagenet` flag |
| P2P Port | 18080 | Inbound connections allowed |
| RPC Port | 18081 | Internal only (Docker net) |
| Pruning | Enabled | `--prune-blockchain` saves ~70% disk |
| Storage | ~50-60 GB | Grows slowly with pruning |

### 2. monero-wallet-rpc

| Setting | Value | Notes |
|---------|-------|-------|
| Image | `ghcr.io/sethforprivacy/simple-monero-wallet-rpc:latest` | Trusted build |
| RPC Port | 18083 | Internal only |
| Auth | HTTP Basic Auth | `WALLET_RPC_USER:WALLET_RPC_PASS` |
| Storage | Varies | Wallet files (view-only, encrypted) |

### 3. Redis

| Setting | Value | Notes |
|---------|-------|-------|
| Image | `redis:7-alpine` | Lightweight |
| Persistence | AOF | `--appendonly yes` |
| Max Memory | 256MB | `maxmemory-policy allkeys-lru` |
| Storage | ~10-100 MB | Depends on user count |

### 4. app-bot (Telegram Bot)

| Setting | Value | Notes |
|---------|-------|-------|
| Mode | `APP_MODE=bot` | Telegram polling only |
| Replicas | 1 | Telegram webhook limits to 1 |
| Restart | unless-stopped | Manual restart on crash |

### 5. app-monitor (Payment Monitor)

| Setting | Value | Notes |
|---------|-------|-------|
| Mode | `APP_MODE=monitor` | Blockchain polling only |
| Replicas | 1+ | Can scale horizontally |
| Interval | 30s | `monitor_interval_sec` env var |

## Scaling Strategy

### Current: Single Node (Combined)
```bash
docker compose -f docker-compose.yml \
               -f docker-compose.mainnet.yml \
               -f docker-compose.production.yml \
               up -d
```

### Scale: Separate Bot + Monitor
```bash
# Bot only (1 replica due to Telegram polling)
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

### Future: Multi-Host
- Bot: Single instance with Telegram webhook (requires HTTPS endpoint)
- Monitor: Kubernetes/Docker Swarm with shared Redis
- Monerod: Dedicated node or external RPC provider

## Networking

```yaml
# Internal Docker network - no external exposure
networks:
  xmr-bot-net:
    driver: bridge
    internal: false  # monerod needs P2P access
```

### Port Exposure

| Service | External | Internal | Purpose |
|---------|----------|----------|---------|
| monerod P2P | 18080/tcp | - | Blockchain sync |
| monerod RPC | - | 18081/tcp | Wallet queries |
| wallet-rpc | - | 18083/tcp | App queries |
| redis | - | 6379/tcp | State store |

**No host ports bound for app services** — all internal.

## Security Hardening

### 1. Firewall (UFW)
```bash
# Default deny incoming
ufw default deny incoming
ufw default allow outgoing

# SSH (adjust port if needed)
ufw allow 22/tcp

# Monero P2P
ufw allow 18080/tcp

# Enable
ufw enable
```

### 2. Docker Security
- Containers run with read-only root fs where possible
- `appuser` non-root user in app containers
- No `--privileged` flags
- Resource limits defined in production compose

### 3. Secrets Management
- `.env` file: mode 0600, owned by deploy user
- Encryption keys generated via `/dev/urandom`
- Wallet files in named volume (not bind mount)
- No secrets in logs or environment dumps

## Resource Requirements

### Minimum (Single Node)
| Resource | Value | Notes |
|----------|-------|-------|
| CPU | 2 cores | monerod is CPU intensive during sync |
| RAM | 4 GB | 2GB for monerod, 1GB for others |
| Disk | 100 GB SSD | 60GB for pruned chain, 40GB growth buffer |
| Bandwidth | 100 GB/month | Sync + P2P traffic |

### Recommended (Production)
| Resource | Value | Notes |
|----------|-------|-------|
| CPU | 4 cores | Faster sync, headroom |
| RAM | 8 GB | Comfortable for growth |
| Disk | 200 GB NVMe | IOPS matters for monerod |
| Bandwidth | Unlimited | P2P is unpredictable |

## Monitoring Stack (Optional)

### Prometheus + Grafana
```yaml
# Included in docker-compose.production.yml (commented)
services:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    
  grafana:
    image: grafana/grafana:latest
    ports:
      - "127.0.0.1:3000:3000"  # Localhost only, use SSH tunnel
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/dashboards:/etc/grafana/provisioning/dashboards
```

### Key Metrics
- `monerod`: block height, sync status, peer count
- `wallet-rpc`: response time, error rate
- `app`: cheque count, payment processing latency
- `system`: CPU, RAM, disk I/O

### Health Checks
All services have Docker health checks defined:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:18081/get_height"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 60s
```

## Backup Strategy

### What to Backup
| Path | Frequency | Retention | Method |
|------|-----------|-----------|--------|
| `wallet_files` volume | Daily | 7 days | Docker volume backup |
| `redis_data` volume | Hourly | 24 hours | Redis BGSAVE + copy |
| `.env` file | Once | Forever | Secure offsite storage |
| User data (Redis) | Real-time | - | Redis AOF already durable |

### Automated Backup Script
Located at `scripts/backup.sh` — see runbook for usage.

## Log Management

### Docker Logging
```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

### Log Aggregation (Optional)
- Vector/Fluentd sidecar for centralized logging
- Or simple logrotate for local retention

## Updates & Maintenance

### Image Updates
```bash
# Pull new images
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml -f docker-compose.production.yml pull

# Rolling restart
docker compose up -d --build
```

### Monerod Upgrades
- monerod images auto-update via `:latest` tag
- Hard fork handling: monitor Monero announcements
- Major version: test on stagenet first

See UPGRADE-ROLLBACK-RUNBOOK.md for detailed procedures.
