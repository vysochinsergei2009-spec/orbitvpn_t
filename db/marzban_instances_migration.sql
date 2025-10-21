-- Migration script for Marzban-Nodes architecture
-- This creates the marzban_instances table for managing multiple Marzban panel instances

CREATE TABLE IF NOT EXISTS marzban_instances (
    id VARCHAR(50) PRIMARY KEY,  -- e.g., "s001", "s002", "eu001"
    name VARCHAR(255),            -- Friendly name for display
    base_url TEXT NOT NULL,       -- Marzban panel URL (e.g., https://panel.example.com:8000/)
    username TEXT NOT NULL,       -- Marzban admin username
    password TEXT NOT NULL,       -- Marzban admin password
    is_active BOOLEAN DEFAULT TRUE,  -- Enable/disable instance
    priority INTEGER DEFAULT 100,    -- Lower = higher priority for load balancing
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index on is_active and priority for faster queries
CREATE INDEX IF NOT EXISTS idx_marzban_instances_active_priority
ON marzban_instances(is_active, priority)
WHERE is_active = TRUE;

-- Insert initial instance from existing config (S001)
-- This migration assumes you have S001_BASE_URL, S001_MARZBAN_USERNAME, S001_MARZBAN_PASSWORD in .env
-- Run this after creating the table:

-- Example insert (replace with actual values from your .env):
-- INSERT INTO marzban_instances (id, name, base_url, username, password, is_active, priority)
-- VALUES (
--     's001',
--     'Main Marzban Server',
--     'https://s001.orbitcorp.space:8000/',
--     'admin',  -- Replace with actual username
--     'password',  -- Replace with actual password
--     TRUE,
--     100
-- );

-- Note: After running this migration, you should:
-- 1. Manually insert your Marzban instance(s) using INSERT statement above
-- 2. Update configs.server_id to reference marzban_instances.id instead of servers.id
-- 3. Consider deprecating the 'servers' table once migration is complete
