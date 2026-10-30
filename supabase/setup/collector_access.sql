-- Optional: run as a trusted database owner after the telemetry migration.
-- Adds only a NOLOGIN group role; no credentials are created or printed.
begin;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'sherlock_audit_source') then
    create role sherlock_audit_source nologin;
  end if;
end $$;
grant usage on schema auth to sherlock_audit_source;
grant select (id, created_at, payload) on auth.audit_log_entries to sherlock_audit_source;
do $$ begin
  if exists (select 1 from information_schema.columns where table_schema = 'auth'
      and table_name = 'audit_log_entries' and column_name = 'ip_address') then
    grant select (ip_address) on auth.audit_log_entries to sherlock_audit_source;
  end if;
end $$;
commit;
