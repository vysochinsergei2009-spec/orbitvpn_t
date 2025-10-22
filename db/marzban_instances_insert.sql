-- Insert script for populating marzban_instances table
-- Run this after marzban_instances_migration.sql

-- Insert your first Marzban instance (s001)
-- IMPORTANT: Update the username and password with actual values from your .env file

INSERT INTO marzban_instances (id, name, base_url, username, password, is_active, priority)
VALUES (
    's001',
    'Main Marzban Server',
    'https://s001.orbitcorp.space:8000/',
    'sanenh',
    '8457',
    TRUE,
    100
)
ON CONFLICT (id) DO UPDATE SET
    base_url = EXCLUDED.base_url,
    username = EXCLUDED.username,
    password = EXCLUDED.password,
    is_active = EXCLUDED.is_active,
    priority = EXCLUDED.priority,
    updated_at = CURRENT_TIMESTAMP;

-- Example for adding additional instances in the future:
-- INSERT INTO marzban_instances (id, name, base_url, username, password, is_active, priority)
-- VALUES (
--     's002',
--     'Europe Marzban Server',
--     'https://eu.orbitcorp.space:8000/',
--     'admin',
--     'password',
--     TRUE,
--     200  -- Lower priority than s001
-- );
