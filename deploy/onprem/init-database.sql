-- Runs only for a new PostgreSQL volume. The application is not a superuser.
\set app_password `cat /run/secrets/database_password`
CREATE ROLE integrity LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
CREATE DATABASE integrity OWNER integrity;
