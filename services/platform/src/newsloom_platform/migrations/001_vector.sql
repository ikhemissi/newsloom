CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON DATABASE newsloom FROM PUBLIC;
GRANT CONNECT ON DATABASE newsloom TO newsloom_ingestion, newsloom_enrichment, newsloom_mcp;
