-- =============================================================================
-- Varsha — Database Initialization
-- Runs automatically on first docker compose up via initdb.d
-- =============================================================================

-- Enable PostGIS
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Log
DO $$ BEGIN RAISE NOTICE 'PostGIS extensions enabled for Varsha'; END $$;
