# OrbitVPN Service Manager

Comprehensive management system for OrbitVPN Telegram bot and Marzban VPN infrastructure with both CLI and Web interfaces.

## Features

### 🎯 Core Capabilities
- **Service Management**: Start, stop, restart, and monitor all services
- **Health Monitoring**: Automatic health checks with configurable intervals
- **Metrics Collection**: Real-time CPU, memory, and custom metrics
- **Auto-Recovery**: Automatic restart of failed services with configurable policies
- **Alert System**: Telegram notifications for critical events
- **Multi-Instance Marzban**: Monitor and manage multiple Marzban panels and nodes

### 💻 Two Powerful Interfaces

#### 1. CLI Interface
Beautiful terminal interface with rich visualizations using Rich library:
- Service status with color-coded health indicators
- Marzban infrastructure tree view
- Redis cache management
- Real-time metrics and statistics
- Interactive commands for all operations

#### 2. Web Dashboard
Modern web interface accessible via browser:
- Real-time service status and metrics
- Interactive charts and graphs
- Marzban nodes visualization
- User statistics
- Service control (start/stop/restart)
- Authentication and session management

## Installation

### Prerequisites
- Python 3.10+
- PostgreSQL (running)
- Redis (running)
- OrbitVPN bot installed and configured

### Install Dependencies

The manager requires additional dependencies. Add to your `requirements.txt`:

```txt
# Existing dependencies...

# Manager dependencies
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
jinja2>=3.1.2
python-multipart>=0.0.6
psutil>=5.9.0
pyyaml>=6.0
```

Install:
```bash
pip install -r requirements.txt
```

## Configuration

### 1. Initial Setup

The manager uses `manager/config/services.yaml` for configuration. Copy the default config:

```bash
# Config is created automatically on first run
python bot_manager.py info
```

### 2. Configure Web Dashboard Authentication

Edit `manager/config/services.yaml`:

```yaml
monitoring:
  web_dashboard:
    enabled: true
    host: "0.0.0.0"
    port: 8080
    auth_enabled: true
    secret_key: "your-secret-key-here"  # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    admin_users:
      admin: "your-password-hash"  # Generate with: python -c "import hashlib; print(hashlib.sha256(b'your_password').hexdigest())"
```

**Generate Secure Credentials:**

```bash
# Generate secret key
python -c "import secrets; print(secrets.token_hex(32))"

# Generate password hash (replace 'your_password')
python -c "import hashlib; print(hashlib.sha256(b'your_password').hexdigest())"
```

### 3. Configure Telegram Alerts (Optional)

To receive alerts in Telegram:

```yaml
monitoring:
  alerts:
    telegram_enabled: true
    admin_chat_ids:
      - 123456789  # Your Telegram user ID
      - 987654321  # Additional admin IDs
    alert_levels:
      - critical
      - error
```

Get your Telegram ID: Send `/start` to [@userinfobot](https://t.me/userinfobot)

## Usage

### CLI Commands

#### Service Management

```bash
# Start all services
python bot_manager.py start

# Start specific service
python bot_manager.py start telegram_bot

# Stop all services
python bot_manager.py stop

# Stop specific service (graceful)
python bot_manager.py stop telegram_bot

# Force stop (no graceful shutdown)
python bot_manager.py stop telegram_bot --force

# Restart service
python bot_manager.py restart telegram_bot
```

#### Status and Health

```bash
# Show status of all services
python bot_manager.py status

# Perform health check
python bot_manager.py health

# Show metrics
python bot_manager.py metrics

# Show metrics for specific service with history
python bot_manager.py metrics telegram_bot --hours 24
```

#### Marzban Management

```bash
# List all Marzban instances and nodes
python bot_manager.py marzban list

# Check specific instance
python bot_manager.py marzban check s001
```

#### Cache Management

```bash
# Show Redis statistics
python bot_manager.py cache stats

# Clear cache by pattern
python bot_manager.py cache clear --pattern "user:*"

# Clear all cache (with confirmation)
python bot_manager.py cache clear

# Clear without confirmation
python bot_manager.py cache clear --yes
```

#### Web Dashboard

```bash
# Start web dashboard (default: http://0.0.0.0:8080)
python bot_manager.py dashboard

# Custom host/port
python bot_manager.py dashboard --host 127.0.0.1 --port 3000

# Development mode with auto-reload
python bot_manager.py dashboard --reload
```

#### Information

```bash
# Show bot configuration
python bot_manager.py info
```

### Web Dashboard Access

1. **Start the dashboard:**
   ```bash
   python bot_manager.py dashboard
   ```

2. **Open browser:**
   ```
   http://your-server-ip:8080
   ```

3. **Login:**
   - Default username: `admin`
   - Default password: `admin` (hash in config file)

   **⚠️ IMPORTANT: Change the default password in production!**

### Dashboard Features

#### Main Dashboard
- **Service Cards**: Real-time status, health, CPU, memory, uptime
- **User Statistics**: Total users, active subscriptions, new users
- **Marzban Overview**: Instances and nodes health
- **Metrics Charts**: Historical performance data
- **Quick Actions**: Start/stop/restart services with one click

#### Services Page
- Detailed service information
- Log viewing (real-time for bot)
- Individual service metrics

#### Marzban Page
- All instances and nodes
- Load distribution
- User statistics per instance
- Node health status

#### Metrics Page
- Historical metrics charts
- CPU and memory trends
- Custom metrics per service

## Architecture

### Directory Structure

```
manager/
├── core/                    # Core components
│   ├── supervisor.py        # Main service supervisor
│   ├── service.py           # Base service abstraction
│   ├── health.py            # Health checking system
│   ├── metrics.py           # Metrics collection
│   └── models.py            # Data models
├── services/                # Service implementations
│   ├── telegram_bot.py      # Telegram bot service
│   ├── marzban.py           # Marzban monitor
│   ├── redis.py             # Redis monitor
│   └── postgres.py          # PostgreSQL monitor
├── monitoring/              # Monitoring & alerts
│   ├── alerts.py            # Alert management
│   └── telegram_notifier.py # Telegram notifications
├── web/                     # Web dashboard
│   ├── app.py               # FastAPI application
│   ├── templates/           # Jinja2 templates
│   └── static/              # CSS, JS files
├── config/                  # Configuration
│   ├── manager_config.py    # Config models
│   └── services.yaml        # User configuration
├── utils/                   # Utilities
│   └── logger.py            # Logging setup
└── cli.py                   # CLI interface
```

### Service Lifecycle

1. **Registration**: Services register with supervisor
2. **Health Checks**: Periodic checks (configurable interval)
3. **Metrics Collection**: Automatic collection of system metrics
4. **Auto-Restart**: Failed services restart based on policy
5. **Alerting**: Critical events trigger alerts

### Restart Policies

Configure in `services.yaml`:

- **always**: Restart on any failure (default for bot)
- **on-failure**: Restart only on crash
- **never**: No automatic restart

```yaml
services:
  telegram_bot:
    restart_policy: always
    max_restarts: 5  # Give up after 5 attempts
    restart_delay: 10  # Wait 10s between attempts
```

## Monitoring

### Health Status Levels

- **🟢 Healthy**: Service operating normally
- **🟡 Degraded**: Service running but with issues (high latency, etc.)
- **🔴 Unhealthy**: Service down or not responding
- **⚪ Unknown**: Status cannot be determined

### Metrics Collected

**All Services:**
- CPU usage (%)
- Memory usage (MB and %)
- Uptime (seconds)
- Restart count

**Telegram Bot:**
- Process ID
- Tmux session status
- Log file size

**Marzban:**
- Total instances
- Total users across all instances
- Active users
- Node count and health

**Redis:**
- Latency (ms)
- Total keys
- Memory usage
- Hit rate (%)
- Connected clients

**PostgreSQL:**
- Database size
- Active connections
- Query performance
- Table statistics

## Alerts

### Alert Levels

1. **INFO**: Informational messages
2. **WARNING**: Potential issues
3. **ERROR**: Service errors
4. **CRITICAL**: Service failures

### Alert Rate Limiting

Prevents alert spam:
- Minimum 5 minutes between duplicate alerts (configurable)
- Configurable per alert level

### Telegram Alert Format

```
🚨 OrbitVPN Alert

Level: CRITICAL
Service: telegram_bot
Message: Service failed and exceeded max restart attempts (5)
Time: 2025-10-31 15:30:45

Details:
  • restart_count: 5
  • max_restarts: 5
  • health_status: unhealthy
```

## Troubleshooting

### Common Issues

#### 1. "No module named 'manager'"

Ensure you're running from the project root:
```bash
cd /root/orbitvpn
python bot_manager.py status
```

#### 2. Dashboard won't start

Check if port is available:
```bash
sudo netstat -tlnp | grep 8080
```

Change port in config if needed:
```yaml
web_dashboard:
  port: 3000
```

#### 3. Services showing as "unknown"

Wait for first health check cycle (30 seconds by default), or run:
```bash
python bot_manager.py health
```

#### 4. Marzban instances not detected

Ensure instances are in database:
```bash
# Connect to PostgreSQL
psql -U postgres -d orbitvpn

# Check instances
SELECT id, name, is_active FROM marzban_instances;
```

#### 5. Can't login to dashboard

Reset admin password:
```bash
# Generate new hash
python -c "import hashlib; print(hashlib.sha256(b'newpassword').hexdigest())"

# Update in manager/config/services.yaml
```

### Logs

Manager logs are in:
```
/root/orbitvpn/logs/manager.log
/root/orbitvpn/logs/dashboard.log
```

View logs:
```bash
tail -f /root/orbitvpn/logs/manager.log
```

## Advanced Usage

### Custom Health Checks

Services can implement custom health checks. Example for Marzban:

```python
async def health_check(self) -> HealthCheckResult:
    # Check API connectivity
    # Check node status
    # Return HealthCheckResult
```

### Metrics History

Metrics are stored in-memory with configurable retention:

```yaml
monitoring:
  metrics:
    retention_days: 7  # Keep 7 days of metrics
```

Access via API:
```
GET /api/metrics/history?service=telegram_bot&hours=24
```

### Prometheus Export (Future)

Enable Prometheus metrics export:

```yaml
monitoring:
  metrics:
    prometheus_export: true
    prometheus_port: 9090
```

## Security Best Practices

1. **Change Default Credentials**
   ```bash
   # Generate strong password
   openssl rand -base64 32

   # Hash it
   python -c "import hashlib; print(hashlib.sha256(b'your_strong_password').hexdigest())"
   ```

2. **Use Firewall**
   ```bash
   # Allow only your IP
   sudo ufw allow from YOUR_IP to any port 8080
   ```

3. **Enable HTTPS**
   Use reverse proxy (nginx/caddy) with SSL certificate

4. **Restrict Dashboard Access**
   ```yaml
   web_dashboard:
     host: "127.0.0.1"  # Localhost only
   ```

5. **Regular Password Rotation**
   Change admin password monthly

## Performance Tuning

### For Large Deployments

```yaml
services:
  telegram_bot:
    health_check_interval: 60  # Reduce check frequency

  marzban_monitor:
    check_interval: 120  # Check Marzban less often

monitoring:
  metrics:
    collect_interval: 30  # Collect metrics every 30s
    retention_days: 3  # Reduce retention
```

### Memory Optimization

Metrics are kept in deque with max size of 1000 data points per service.

## API Reference

### REST API Endpoints

#### Authentication
- `POST /api/login` - Login
- `POST /api/logout` - Logout

#### Services
- `GET /api/status` - System status
- `GET /api/services` - All services info
- `POST /api/services/{name}/start` - Start service
- `POST /api/services/{name}/stop` - Stop service
- `POST /api/services/{name}/restart` - Restart service

#### Marzban
- `GET /api/marzban/instances` - List instances
- `GET /api/marzban/instances/{id}` - Instance details

#### Metrics
- `GET /api/metrics/history` - Metrics history

#### Users
- `GET /api/users/stats` - User statistics

### WebSocket Endpoints

- `WS /ws/logs/{service_name}` - Real-time logs

## Support

For issues, questions, or contributions:
- Check logs first: `/root/orbitvpn/logs/`
- Review configuration: `manager/config/services.yaml`
- Test individual components with CLI

## License

Part of OrbitVPN project.
