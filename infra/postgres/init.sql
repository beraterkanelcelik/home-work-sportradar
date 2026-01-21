-- Database initialization script
-- This script runs when the database container is first created

-- Create extensions
\i /docker-entrypoint-initdb.d/extensions.sql

-- Create databases
CREATE DATABASE langfuse_db;
CREATE DATABASE temporal_db;

-- Configure PostgreSQL for high concurrency
-- Note: These settings are also in postgresql.conf, but we set them here
-- to ensure they're applied even if the config file isn't mounted
ALTER SYSTEM SET max_connections = 500;
ALTER SYSTEM SET shared_buffers = '1GB';
ALTER SYSTEM SET effective_cache_size = '2GB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET work_mem = '32MB';
ALTER SYSTEM SET statement_timeout = '30s';

-- Additional initialization can go here
-- For example, creating initial schemas or users
