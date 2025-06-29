-- 02_schemas.sql
-- Create schemas, users, and set permissions

-- Create database user (only if not exists, and grant CREATEDB)
-- This role will be the owner of the schemas and default for table creation
DO
$do$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'mariupol_researcher') THEN
      CREATE USER mariupol_researcher WITH PASSWORD 'REDACTED' LOGIN CREATEDB;
   END IF;
END
$do$;

-- Grant CONNECT privilege to the database
GRANT CONNECT ON DATABASE mariupol_toponyms TO mariupol_researcher;

-- Create schemas (owned by mariupol_researcher)
CREATE SCHEMA IF NOT EXISTS toponyms AUTHORIZATION mariupol_researcher;
CREATE SCHEMA IF NOT EXISTS audit AUTHORIZATION mariupol_researcher;
CREATE SCHEMA IF NOT EXISTS staging AUTHORIZATION mariupol_researcher;

-- Grant USAGE on schemas to mariupol_researcher (redundant if owned, but harmless)
GRANT USAGE ON SCHEMA toponyms TO mariupol_researcher;
GRANT USAGE ON SCHEMA audit TO mariupol_researcher;
GRANT USAGE ON SCHEMA staging TO mariupol_researcher;

-- Set default search path for mariupol_researcher (and globally for the database for new connections)
ALTER ROLE mariupol_researcher SET search_path TO toponyms, public;
ALTER DATABASE mariupol_toponyms SET search_path TO toponyms, public;

-- Grant default privileges on future tables within schemas to mariupol_researcher
ALTER DEFAULT PRIVILEGES FOR ROLE mariupol_researcher IN SCHEMA toponyms GRANT ALL PRIVILEGES ON TABLES TO mariupol_researcher;
ALTER DEFAULT PRIVILEGES FOR ROLE mariupol_researcher IN SCHEMA audit GRANT ALL PRIVILEGES ON TABLES TO mariupol_researcher;
ALTER DEFAULT PRIVILEGES FOR ROLE mariupol_researcher IN SCHEMA staging GRANT ALL PRIVILEGES ON TABLES TO mariupol_researcher;

-- Make mariupol_researcher the owner of the database itself
ALTER DATABASE mariupol_toponyms OWNER TO mariupol_researcher;

-- Comments for documentation
COMMENT ON SCHEMA toponyms IS 'Current toponymic entities and names';
COMMENT ON SCHEMA audit IS 'Complete audit trail for legal compliance';
COMMENT ON SCHEMA staging IS 'Temporary tables for data import and validation';
