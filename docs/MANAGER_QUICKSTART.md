# OrbitVPN Manager - Quick Start Guide

## 5-Minute Setup

### Step 1: Install Dependencies

```bash
cd /root/orbitvpn

# Add to requirements.txt:
cat >> requirements.txt << 'EOF'

# Manager dependencies
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
jinja2>=3.1.2
python-multipart>=0.0.6
psutil>=5.9.0
pyyaml>=6.0
EOF

# Install
pip install -r requirements.txt
```

### Step 2: Initial Configuration

```bash
# Generate secure credentials
python << 'EOF'
import secrets
import hashlib

# Secret key for sessions
secret = secrets.token_hex(32)
print(f"Secret Key: {secret}")

# Password hash (change 'mypassword' to your password)
password = "mypassword"
pwd_hash = hashlib.sha256(password.encode()).hexdigest()
print(f"Password Hash: {pwd_hash}")
EOF
```

Update `manager/config/services.yaml`:
- Replace `secret_key` with generated key
- Replace admin password hash
- Add your Telegram ID to `admin_chat_ids` (optional)

### Step 3: Test CLI

```bash
# View status
python bot_manager.py status

# Health check
python bot_manager.py health

# View Marzban
python bot_manager.py marzban list

# Cache stats
python bot_manager.py cache stats
```

### Step 4: Start Web Dashboard

```bash
# Start dashboard
python bot_manager.py dashboard

# Or run in background
nohup python bot_manager.py dashboard > /dev/null 2>&1 &
```

Access at: `http://your-server-ip:8080`

**Login:**
- Username: `admin`
- Password: (what you set in config)

### Step 5: Common Operations

```bash
# Start bot
python bot_manager.py start telegram_bot

# View metrics
python bot_manager.py metrics

# Clear cache
python bot_manager.py cache clear --pattern "user:*"

# Restart service
python bot_manager.py restart telegram_bot
```

## Quick Reference

### Service Management
```bash
python bot_manager.py start [service]    # Start
python bot_manager.py stop [service]     # Stop
python bot_manager.py restart [service]  # Restart
python bot_manager.py status             # Status
```

### Monitoring
```bash
python bot_manager.py health                  # Health check
python bot_manager.py metrics [service]       # Metrics
python bot_manager.py marzban list            # Marzban nodes
```

### Cache
```bash
python bot_manager.py cache stats             # Statistics
python bot_manager.py cache clear -p "key:*"  # Clear pattern
```

### Web Dashboard
```bash
python bot_manager.py dashboard               # Start
python bot_manager.py dashboard --port 3000   # Custom port
```

## Firewall Setup (Optional)

```bash
# Allow dashboard access
sudo ufw allow 8080/tcp

# Or restrict to your IP
sudo ufw allow from YOUR_IP to any port 8080
```

## Systemd Service (Production)

Create `/etc/systemd/system/orbitvpn-manager.service`:

```ini
[Unit]
Description=OrbitVPN Manager Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/orbitvpn
ExecStart=/root/orbitvpn/venv/bin/python /root/orbitvpn/bot_manager.py dashboard
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable orbitvpn-manager
sudo systemctl start orbitvpn-manager
sudo systemctl status orbitvpn-manager
```

## Nginx Reverse Proxy (HTTPS)

```nginx
server {
    listen 80;
    server_name manager.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

Then add SSL with Let's Encrypt:
```bash
sudo certbot --nginx -d manager.yourdomain.com
```

## Troubleshooting

### Can't connect to dashboard
```bash
# Check if running
ps aux | grep "bot_manager.py dashboard"

# Check port
sudo netstat -tlnp | grep 8080

# Check logs
tail -f /root/orbitvpn/logs/dashboard.log
```

### Services show "unknown"
```bash
# Wait 30 seconds or force health check
python bot_manager.py health
```

### Forgot password
```bash
# Generate new hash
python -c "import hashlib; print(hashlib.sha256(b'newpassword').hexdigest())"

# Update manager/config/services.yaml
```

## Next Steps

1. ✅ Read full documentation: `MANAGER_README.md`
2. ✅ Configure Telegram alerts
3. ✅ Set up automatic monitoring
4. ✅ Create systemd service for dashboard
5. ✅ Configure HTTPS with reverse proxy

## Support

Check logs:
```bash
# Manager logs
tail -f /root/orbitvpn/logs/manager.log

# Dashboard logs
tail -f /root/orbitvpn/logs/dashboard.log

# Bot logs
tail -f /root/orbitvpn/bot.log
```

That's it! You're ready to manage your OrbitVPN infrastructure! 🚀
