CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA newsloom_acceptance_admin;
REVOKE ALL ON SCHEMA newsloom_acceptance_admin FROM PUBLIC;
CREATE TABLE newsloom_acceptance_admin.manifest (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    payload jsonb NOT NULL,
    started boolean NOT NULL DEFAULT false
);
CREATE TABLE newsloom_acceptance_admin.schema_migrations (
    version text PRIMARY KEY,
    checksum text NOT NULL CHECK (checksum ~ '^[a-f0-9]{64}$')
);
