# Marzban-Nodes Architecture

This document describes the new architecture for managing VPN servers using Marzban with node support.

## Overview

The bot now supports **multiple Marzban panel instances**, each of which can manage **multiple nodes** internally. This architecture provides:

- **Scalability**: Add new Marzban instances easily by inserting into database
- **Load Balancing**: Automatic selection of least-loaded node across all instances
- **Geographic Distribution**: Deploy Marzban instances in different regions
- **High Availability**: Multiple instances provide redundancy

## Architecture Components

### 1. MarzbanInstance Model (`app/repo/models.py`)

Represents a Marzban panel instance in the database:

```python
class MarzbanInstance:
    id: str                  # e.g., "s001", "eu001"
    name: str               # Friendly name
    base_url: str           # Marzban panel URL
    username: str           # Admin username
    password: str           # Admin password
    is_active: bool         # Enable/disable
    priority: int           # Lower = higher priority
    created_at: datetime
    updated_at: datetime
```

### 2. MarzbanClient (`app/repo/marzban_client.py`)

Centralized client for interacting with multiple Marzban instances:

**Key Features:**
- Fetches all active Marzban instances from database
- Queries each instance for its nodes and usage metrics
- Calculates load score for each node based on:
  - Active users count
  - Usage coefficient (node weight)
  - Traffic volume (uplink + downlink)
- Selects least-loaded node automatically
- Provides methods: `add_user()`, `remove_user()`, `modify_user()`

**Load Balancing Formula:**
```python
load_score = (active_users × 100 × usage_coefficient) + (traffic_gb × 1)
```
Lower score = less loaded = better choice.

### 3. Updated UserRepository (`app/repo/user.py`)

The `create_and_add_config()` method now:
- No longer requires `server_id` parameter
- Uses `MarzbanClient` to auto-select best instance/node
- Supports optional `manual_instance_id` for future server selection feature
- Stores Marzban instance ID in `configs.server_id` field

### 4. Database Schema

**New Table: `marzban_instances`**
```sql
CREATE TABLE marzban_instances (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(255),
    base_url TEXT NOT NULL,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 100,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Modified Field:**
- `configs.server_id` now stores `marzban_instances.id` instead of `servers.id`

**Deprecated Table:**
- `servers` table is kept for backward compatibility but no longer used by new code

## Migration Guide

### Step 1: Run Database Migration

```bash
# Create marzban_instances table
psql -U $DATABASE_USER -d $DATABASE_NAME -f db/marzban_instances_migration.sql

# Insert your first instance (edit credentials first!)
psql -U $DATABASE_USER -d $DATABASE_NAME -f db/marzban_instances_insert.sql
```

### Step 2: Update Credentials in SQL

Edit `db/marzban_instances_insert.sql` and replace:
```sql
'admin',  -- Replace with S001_MARZBAN_USERNAME from .env
'your_password_here',  -- Replace with S001_MARZBAN_PASSWORD from .env
```

### Step 3: Verify Migration

```sql
SELECT * FROM marzban_instances WHERE is_active = TRUE;
```

You should see your s001 instance listed.

### Step 4: Test Config Creation

Create a test config through the bot. Check logs for:
```
INFO: Selected node <node_name> (ID: <node_id>) on instance s001 with load score <score>
INFO: Config created for user <tg_id> on Marzban instance s001
```

## Adding More Marzban Instances

To add additional instances for scaling:

```sql
INSERT INTO marzban_instances (id, name, base_url, username, password, is_active, priority)
VALUES (
    'eu001',
    'Europe Server',
    'https://eu.orbitcorp.space:8000/',
    'admin',
    'password',
    TRUE,
    200  -- Higher priority number = lower priority (will be used if s001 overloaded)
);
```

## How Node Selection Works

1. **Fetch Active Instances**: Query database for all active Marzban instances, ordered by priority
2. **Get Node Metrics**: For each instance, call Marzban API:
   - `get_nodes()` - List of nodes with ID, name, usage_coefficient
   - `get_nodes_usage()` - Traffic stats (uplink, downlink)
   - `get_users()` - Count active users (approximated per node)
3. **Calculate Load Scores**: For each node across all instances
4. **Select Best**: Choose node with lowest load score
5. **Create User**: Call `add_user()` on the selected instance
6. **Store Metadata**: Save instance ID to `configs.server_id` for future operations

## Future Enhancements

### User-Selectable Servers

The architecture supports manual instance selection via `manual_instance_id` parameter:

```python
await user_repo.create_and_add_config(
    tg_id=user_id,
    manual_instance_id="eu001"  # User chooses Europe server
)
```

To implement:
1. Add keyboard with server location options
2. Pass selected instance ID to `create_and_add_config()`
3. Update locales with server names

### Improved Load Metrics

Current implementation approximates users per node. Future improvements:
- Wait for Marzban API to expose per-node user counts
- Implement caching layer for node metrics (TTL: 60s)
- Add CPU/Memory metrics if Marzban exposes them

### Multi-Region Deployment

Deploy Marzban instances in different regions:
```
s001 (USA)    → Priority 100
eu001 (EU)    → Priority 100
as001 (Asia)  → Priority 100
```

Bot will auto-balance across all regions.

## Troubleshooting

### No Active Instances Error

**Error:** `ValueError: No active Marzban instances available`

**Solution:**
1. Check database: `SELECT * FROM marzban_instances WHERE is_active = TRUE;`
2. Verify instance credentials in database match actual Marzban panel
3. Check Marzban panel is accessible from bot server

### Config Creation Fails

**Check logs for:**
- Connection errors → Verify `base_url` is correct
- Auth errors → Verify `username`/`password` are correct
- API errors → Check Marzban panel version compatibility (tested with v0.8.4)

### Load Balancing Not Working

**Symptoms:** All users go to same node

**Possible causes:**
1. Only one active instance in database
2. Only one node configured in Marzban
3. Load calculation needs tuning (adjust weights in `NodeLoadMetrics.load_score`)

## Code References

- **MarzbanClient**: `app/repo/marzban_client.py`
- **MarzbanInstance Model**: `app/repo/models.py:64`
- **Updated create_and_add_config**: `app/repo/user.py:351`
- **Handler Update**: `app/core/handlers.py:111`
- **Migration SQL**: `db/marzban_instances_migration.sql`

## Backward Compatibility

The old `Server` model and `ServerRepository` are **deprecated but not removed**:
- Marked with deprecation warnings in code
- Kept for backward compatibility with existing data
- Will be removed in future major version

Existing configs with old `server_id` values will continue to work, but new configs use the new architecture.
