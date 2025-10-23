-- Migration: Add excluded_node_names column to marzban_instances
-- This allows excluding specific nodes from load balancing while keeping them active for existing users

ALTER TABLE marzban_instances
ADD COLUMN IF NOT EXISTS excluded_node_names TEXT[] DEFAULT '{}';

COMMENT ON COLUMN marzban_instances.excluded_node_names IS 'Array of node names to exclude from automatic load balancing';
