# VPS Provisioning Checklist — XMR Cheque Bot Production

Use this checklist when setting up a new VPS for XMR Cheque Bot mainnet deployment.

## Pre-Provisioning

- [ ] Domain name registered (optional, for webhook mode)
- [ ] Telegram bot token created (@BotFather)
- [ ] VPS provider selected (recommended: 4 vCPU, 8GB RAM, 200GB NVMe)
- [ ] SSH key generated for deploy user: `ssh-keygen -t ed25519 -C "xmr-bot-deploy"`

## VPS Specifications

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Disk | 100 GB SSD | 200 GB NVMe |
| Network | 100 GB/mo | Unlimited |

## Phase 1: Initial Server Setup

### 1.1 System Update
```bash
# Update packages
sudo apt update && sudo apt upgrade -y

# Install essentials
sudo apt install -y curl wget git ufw fail2ban htop ncdu
```

- [ ] System packages updated
- [ ] Essential tools installed

### 1.2 Create Deploy User
```bash
# Create deploy user
sudo adduser --disabled-password --gecos "" xmrbot
sudo usermod -aG sudo xmrbot

# Set up SSH key
sudo mkdir -p /home/xmrbot/.ssh
sudo bash -c 'cat > /home/xmrbot/.ssh/authorized_keys' << 'EOF'
# Paste your SSH public key here
EOF
sudo chmod 700 /home/xmrbot/.ssh
sudo chmod 600 /home/xmrbot/.ssh/authorized_keys
sudo chown -R xmrbot:xmrbot /home/xmrbot/.ssh
```

- [ ] Deploy user `xmrbot` created
- [ ] SSH key added
- [ ] User added to sudo group

### 1.3 SSH Hardening
```bash
sudo nano /etc/ssh/sshd_config
```

Set these values:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
ClientAliveInterval 300
ClientAliveCountMax 2
```

```bash
sudo systemctl restart sshd
```

- [ ] Root login disabled
- [ ] Password auth disabled
- [ ] Key auth enabled
- [ ] SSH service restarted

### 1.4 Firewall (UFW)
```bash
# Default policies
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH
sudo ufw allow 22/tcp

# Monero P2P (mainnet)
sudo ufw allow 18080/tcp

# Enable firewall
sudo ufw enable
sudo ufw status verbose
```

- [ ] UFW enabled
- [ ] SSH port allowed
- [ ] Monero P2P port (18080) allowed
- [ ] All other incoming traffic blocked

### 1.5 Fail2ban
```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
sudo fail2ban-client status
```

- [ ] fail2ban enabled
- [ ] fail2ban running

### 1.6 Time Synchronization
```bash
sudo apt install -y systemd-timesyncd
sudo systemctl enable systemd-timesyncd
sudo systemctl start systemd-timesyncd
timedatectl status
```

- [ ] NTP sync enabled
- [ ] Time correctly set

## Phase 2: Docker Installation

### 2.1 Install Docker
```bash
# Remove old versions
sudo apt remove docker docker-engine docker.io containerd runc

# Add Docker GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repo
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add deploy user to docker group
sudo usermod -aG docker xmrbot
```

- [ ] Docker installed
- [ ] Deploy user added to docker group
- [ ] Test: `docker run hello-world` works after re-login

### 2.2 Docker Hardening
```bash
# Create daemon.json
sudo mkdir -p /etc/docker
sudo bash -c 'cat > /etc/docker/daemon.json' << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true,
  "userland-proxy": false,
  "no-new-privileges": true
}
EOF

sudo systemctl restart docker
```

- [ ] Docker daemon configured
- [ ] Log rotation enabled
- [ ] Live restore enabled

## Phase 3: Application Setup

### 3.1 Clone Repository
```bash
# Switch to deploy user
sudo su - xmrbot

# Clone repo
git clone https://github.com/Pugg213/xmr-cheque-bot.git /opt/xmr-cheque-bot
cd /opt/xmr-cheque-bot

# Create required directories
mkdir -p scripts monitoring monitoring/grafana/provisioning/dashboards monitoring/grafana/provisioning/datasources systemd backups
```

- [ ] Repository cloned
- [ ] Directory structure created

### 3.2 Environment Configuration
```bash
cd /opt/xmr-cheque-bot

# Generate Fernet key for encryption
python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
# SAVE THIS KEY SECURELY

# Create .env
cat > .env << 'EOF'
# Application mode - production uses bot + monitor separately
APP_MODE=both

# Telegram Bot Token (from @BotFather)
BOT_TOKEN=your_bot_token_here

# monero-wallet-rpc HTTP basic auth
WALLET_RPC_USER=CHANGE_ME_TO_RANDOM_16_CHARS
WALLET_RPC_PASS=CHANGE_ME_TO_RANDOM_32_CHARS

# Encryption key (Fernet key from step above)
VIEW_KEY_ENCRYPTION_KEY=YOUR_FERNET_KEY_HERE

# CoinGecko API key (optional, free tier works)
COINGECKO_API_KEY=

# Logging
LOG_LEVEL=INFO
EOF

# Secure permissions
chmod 600 .env
```

- [ ] `.env` file created
- [ ] BOT_TOKEN set
- [ ] WALLET_RPC_USER/PASS set (random strong values)
- [ ] VIEW_KEY_ENCRYPTION_KEY generated and set
- [ ] File permissions set to 0600

### 3.3 Test Configuration
```bash
cd /opt/xmr-cheque-bot

# Validate compose files parse correctly
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml -f docker-compose.production.yml config > /dev/null && echo "Compose files valid"
```

- [ ] Compose configuration validates

## Phase 4: Backup Setup

### 4.1 Backup Script
```bash
cat > /opt/xmr-cheque-bot/scripts/backup.sh << 'EOFSCRIPT'
#!/bin/bash
set -euo pipefail

BACKUP_DIR="/opt/xmr-cheque-bot/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# Backup Redis data
docker run --rm -v xmr-cheque-bot_redis_data:/data:ro -v "$BACKUP_DIR:/backup" alpine tar czf "/backup/redis_$TIMESTAMP.tar.gz" -C /data .

# Backup wallet files
docker run --rm -v xmr-cheque-bot_wallet_files:/wallet:ro -v "$BACKUP_DIR:/backup" alpine tar czf "/backup/wallets_$TIMESTAMP.tar.gz" -C /wallet .

# Cleanup old backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "[$(date)] Backup complete: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
EOFSCRIPT

chmod +x /opt/xmr-cheque-bot/scripts/backup.sh
```

- [ ] Backup script created

### 4.2 Cron Job
```bash
# Edit crontab for deploy user
crontab -e

# Add:
# Daily backup at 3 AM
0 3 * * * /opt/xmr-cheque-bot/scripts/backup.sh >> /opt/xmr-cheque-bot/backups/backup.log 2>&1
```

- [ ] Cron job configured for daily backups

## Phase 5: Systemd Service (Optional but Recommended)

```bash
sudo bash -c 'cat > /etc/systemd/system/xmr-cheque-bot.service' << 'EOF'
[Unit]
Description=XMR Cheque Bot
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/xmr-cheque-bot
User=xmrbot
Group=xmrbot

# Start
ExecStart=/usr/bin/docker compose \
  -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d

# Stop
ExecStop=/usr/bin/docker compose \
  -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  down

# Reload
ExecReload=/usr/bin/docker compose \
  -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable xmr-cheque-bot.service
```

- [ ] systemd service created
- [ ] Service enabled

## Phase 6: First Start

### 6.1 Initial Deployment
```bash
cd /opt/xmr-cheque-bot

# Pull images first
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml -f docker-compose.production.yml pull

# Start infrastructure (redis, monerod, wallet-rpc)
docker compose -f docker-compose.yml -f docker-compose.mainnet.yml up -d redis monerod

# Wait for monerod to start syncing (check logs)
docker compose logs -f monerod
# Wait until you see "Synced" messages or let it run
```

- [ ] Redis started
- [ ] monerod started and syncing

### 6.2 Wait for Monero Sync (Important!)

**Initial sync takes several hours to days.** Do not proceed until monerod is mostly synced.

```bash
# Check sync status
curl -s http://localhost:18081/get_info | jq '.height,.target_height'
```

When height ≈ target_height, proceed.

- [ ] monerod synced (or close to it)

### 6.3 Start Application
```bash
cd /opt/xmr-cheque-bot

# Start all services
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  up -d

# Check status
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  ps

# View logs
docker compose -f docker-compose.yml \
  -f docker-compose.mainnet.yml \
  -f docker-compose.production.yml \
  logs -f
```

- [ ] All services running
- [ ] No errors in logs
- [ ] Bot responding to /start in Telegram

## Phase 7: Post-Deployment

### 7.1 Health Check
```bash
# Run health check script
cat > /opt/xmr-cheque-bot/scripts/health-check.sh << 'EOF'
#!/bin/bash
echo "=== XMR Cheque Bot Health Check ==="
echo ""
echo "--- Docker Containers ---"
docker ps --filter "name=xmr-bot"
echo ""
echo "--- monerod Sync Status ---"
curl -s http://localhost:18081/get_info 2>/dev/null | jq -r '"Height: \(.height), Target: \(.target_height), Synced: \(.synchronized)"' 2>/dev/null || echo "monerod RPC not accessible"
echo ""
echo "--- Disk Usage ---"
df -h / | tail -1
echo ""
echo "--- Memory Usage ---"
free -h | grep "Mem:"
echo ""
echo "--- Recent Logs (last 5 lines) ---"
docker logs --tail 5 xmr-bot-app-bot 2>/dev/null || echo "App logs not available"
EOF

chmod +x /opt/xmr-cheque-bot/scripts/health-check.sh
/opt/xmr-cheque-bot/scripts/health-check.sh
```

- [ ] Health check script created
- [ ] All services healthy

### 7.2 Log Rotation
```bash
sudo bash -c 'cat > /etc/logrotate.d/xmr-cheque-bot' << 'EOF'
/var/lib/docker/containers/*/*.log {
    rotate 7
    daily
    compress
    size=10M
    missingok
    delaycompress
    copytruncate
}
EOF
```

- [ ] Log rotation configured

### 7.3 Final Security Check
```bash
# Check no secrets in logs
sudo grep -r "BOT_TOKEN\|VIEW_KEY" /var/log/ 2>/dev/null || echo "No secrets in logs - good"

# Check file permissions
ls -la /opt/xmr-cheque-bot/.env

# Check firewall
sudo ufw status verbose

# Check Docker security
docker info 2>/dev/null | grep -i "security\|rootless" || true
```

- [ ] No secrets in logs
- [ ] .env file has correct permissions
- [ ] Firewall active and correct

## Completion

- [ ] All phases completed
- [ ] Documentation updated with VPS IP and details
- [ ] Backup verification tested (restore from backup to verify)
- [ ] Team notified of deployment completion

## Post-Deployment Monitoring

First 24 hours:
- [ ] Check monerod sync progress every few hours
- [ ] Monitor disk space usage
- [ ] Verify bot responds to commands
- [ ] Check backup was created successfully
- [ ] Review logs for errors
