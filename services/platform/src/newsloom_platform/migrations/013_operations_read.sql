GRANT CONNECT ON DATABASE newsloom TO newsloom_operations;
GRANT USAGE ON SCHEMA public, newsloom_admin TO newsloom_operations;
GRANT SELECT ON ALL TABLES IN SCHEMA public, newsloom_admin TO newsloom_operations;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public, newsloom_admin TO newsloom_operations;
ALTER DEFAULT PRIVILEGES IN SCHEMA public, newsloom_admin
    GRANT SELECT ON TABLES TO newsloom_operations;
ALTER DEFAULT PRIVILEGES IN SCHEMA public, newsloom_admin
    GRANT SELECT ON SEQUENCES TO newsloom_operations;
