-- Run this ONCE in the Supabase SQL Editor.
-- Creates a dedicated, SELECT-only role for the Day 5 AI Query Assistant.
-- The app's main dashboard tabs keep using your existing credentials;
-- only the AI-generated-SQL feature uses this restricted role.

CREATE ROLE ai_readonly WITH LOGIN PASSWORD 'CHOOSE-A-STRONG-PASSWORD-HERE';

GRANT CONNECT ON DATABASE postgres TO ai_readonly;
GRANT USAGE ON SCHEMA clean TO ai_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA clean TO ai_readonly;

-- Ensures any future tables you add to the clean schema are also
-- automatically readable by this role, without re-running grants.
ALTER DEFAULT PRIVILEGES IN SCHEMA clean GRANT SELECT ON TABLES TO ai_readonly;

-- Explicitly confirm this role has NO write/DDL ability anywhere:
-- (no CREATE, no INSERT/UPDATE/DELETE grants are ever given above)

-- To connect via the pooler using this role, the username becomes:
--   ai_readonly.<your-project-ref>
-- e.g. ai_readonly.namkclyyxexdntxikzsi
-- Same pooler host/port you already use for the main app.
