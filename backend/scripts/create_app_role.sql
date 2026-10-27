-- Local demo only: the database user the AskData backend runs as.
-- It can read the demo data in schema public and owns schema askdata_app (session history).
-- The postgres user is only used to load the demo datasets.
-- Run after every dataset load (backend/scripts/load_dataset.sh does this) because the load
-- drops and recreates schema public, and on a fresh Docker volume (docker-compose.yml init).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'askdata_reader') THEN
        -- Same local demo password as the postgres user in docker-compose.yml.
        CREATE ROLE askdata_reader LOGIN PASSWORD 'postgres';
    END IF;
END
$$;

-- Demo data: read only.
GRANT USAGE ON SCHEMA public TO askdata_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO askdata_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO askdata_reader;

-- Session history: the reader owns this schema and nothing else.
CREATE SCHEMA IF NOT EXISTS askdata_app AUTHORIZATION askdata_reader;
ALTER SCHEMA askdata_app OWNER TO askdata_reader;
REVOKE ALL ON SCHEMA askdata_app FROM PUBLIC;
DO $$
DECLARE
    item record;
BEGIN
    FOR item IN SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'askdata_app' LOOP
        EXECUTE format('ALTER TABLE askdata_app.%I OWNER TO askdata_reader', item.tablename);
    END LOOP;
END
$$;
