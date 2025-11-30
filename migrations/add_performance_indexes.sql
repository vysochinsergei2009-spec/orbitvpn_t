-- Performance Indexes for OrbitVPN Bot
-- Created: 2025-11-30
-- Phase 1: Critical Optimizations

-- Users table indexes
CREATE INDEX IF NOT EXISTS idx_users_subscription_end
    ON users(subscription_end)
    WHERE subscription_end IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_created_at
    ON users(created_at);

CREATE INDEX IF NOT EXISTS idx_users_referrer
    ON users(referrer_id)
    WHERE referrer_id IS NOT NULL;

-- Payments table indexes
CREATE INDEX IF NOT EXISTS idx_payments_status_method
    ON payments(status, method);

CREATE INDEX IF NOT EXISTS idx_payments_confirmed_at
    ON payments(confirmed_at)
    WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS idx_payments_tx_hash
    ON payments(tx_hash)
    WHERE tx_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payments_comment
    ON payments(comment)
    WHERE comment IS NOT NULL;

-- Prevent duplicate pending payments (Race condition protection)
CREATE UNIQUE INDEX IF NOT EXISTS idx_payments_unique_pending
    ON payments(tg_id, method)
    WHERE status = 'pending';

-- Configs table indexes
CREATE INDEX IF NOT EXISTS idx_configs_tg_id_deleted
    ON configs(tg_id, deleted);

CREATE INDEX IF NOT EXISTS idx_configs_username
    ON configs(username)
    WHERE deleted = false;

-- TonTransactions table indexes
CREATE INDEX IF NOT EXISTS idx_ton_tx_comment_amount
    ON ton_transactions(comment, amount)
    WHERE processed_at IS NULL;

-- Display index creation results
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
    AND indexname LIKE 'idx_%'
ORDER BY tablename, indexname;
