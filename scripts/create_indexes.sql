-- ACAS v2 Database Indexes
-- Run this script to create performance indexes

CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys (user_id);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_token_hash ON refresh_tokens (token_hash);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at ON refresh_tokens (expires_at);

CREATE INDEX IF NOT EXISTS idx_analysis_history_user_id ON analysis_history (user_id);
CREATE INDEX IF NOT EXISTS idx_analysis_history_created_at ON analysis_history (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analysis_history_brand ON analysis_history (brand);

CREATE INDEX IF NOT EXISTS idx_forecast_cache_brand ON forecast_cache (brand);
CREATE INDEX IF NOT EXISTS idx_forecast_cache_created_at ON forecast_cache (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_news_cache_source ON news_cache (source);
CREATE INDEX IF NOT EXISTS idx_news_cache_published_at ON news_cache (published_at DESC);

ANALYZE users;
ANALYZE api_keys;
ANALYZE refresh_tokens;
ANALYZE analysis_history;
ANALYZE forecast_cache;
ANALYZE news_cache;
