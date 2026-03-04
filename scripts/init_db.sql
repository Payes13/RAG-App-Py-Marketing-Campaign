-- Database initialization script for Marketing Campaign AI
-- Run this against the marketing_ai PostgreSQL database as a superuser.

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Customer data (structured)
CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    email VARCHAR(255),
    age INTEGER,
    city VARCHAR(100),
    country VARCHAR(100),
    language VARCHAR(50)
);

-- Flight history
CREATE TABLE IF NOT EXISTS flights (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    route VARCHAR(100),
    origin VARCHAR(100),
    destination VARCHAR(100),
    flight_date DATE,
    travel_class VARCHAR(50)
);

-- Customer preferences
CREATE TABLE IF NOT EXISTS preferences (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES customers(id),
    seat_type VARCHAR(50),
    meal_type VARCHAR(50),
    travel_frequency VARCHAR(50),
    family_size INTEGER
);

-- PDF embeddings (pgvector)
CREATE TABLE IF NOT EXISTS document_embeddings (
    id SERIAL PRIMARY KEY,
    content TEXT,
    embedding vector(1536),
    source_file VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Generated campaigns log
CREATE TABLE IF NOT EXISTS generated_campaigns (
    id SERIAL PRIMARY KEY,
    campaign_file_key VARCHAR(255),
    metadata_file_key VARCHAR(255),
    route VARCHAR(100),
    audience_description TEXT,
    campaign_type VARCHAR(50),
    language VARCHAR(10),
    tokens_used INTEGER,
    generated_at TIMESTAMP DEFAULT NOW()
);

-- CSV file metadata (referenced in security whitelist and CSV ingester)
CREATE TABLE IF NOT EXISTS csv_files (
    id SERIAL PRIMARY KEY,
    s3_key VARCHAR(500) UNIQUE,
    column_names JSONB,
    row_count INTEGER,
    ingested_at TIMESTAMP DEFAULT NOW()
);

-- ── Users and Permissions ─────────────────────────────────────────────────────
-- NOTE: Replace ${DB_READONLY_PASSWORD} and ${DB_APP_PASSWORD} with actual values
-- stored in AWS Secrets Manager before running.

-- User 1: read-only (used by LangChain Agent SQL tool)
-- CREATE USER marketing_ai_readonly WITH PASSWORD '${DB_READONLY_PASSWORD}';
-- GRANT CONNECT ON DATABASE marketing_ai TO marketing_ai_readonly;
-- GRANT USAGE ON SCHEMA public TO marketing_ai_readonly;
-- GRANT SELECT ON customers, flights, preferences, document_embeddings, generated_campaigns, csv_files TO marketing_ai_readonly;
-- REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM marketing_ai_readonly;

-- User 2: app user (used by application write operations)
-- CREATE USER marketing_ai_app WITH PASSWORD '${DB_APP_PASSWORD}';
-- GRANT CONNECT ON DATABASE marketing_ai TO marketing_ai_app;
-- GRANT USAGE ON SCHEMA public TO marketing_ai_app;
-- GRANT SELECT, INSERT ON generated_campaigns TO marketing_ai_app;
-- GRANT SELECT, INSERT ON document_embeddings TO marketing_ai_app;
-- GRANT SELECT, INSERT ON csv_files TO marketing_ai_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO marketing_ai_app;
-- REVOKE ALL ON customers FROM marketing_ai_app;
-- REVOKE ALL ON flights FROM marketing_ai_app;
-- REVOKE ALL ON preferences FROM marketing_ai_app;
