-- Run as a trusted owner after the telemetry migration. The view owner must
-- retain SELECT on the source and be able to read its RLS-protected rows.
-- Hosted Supabase's postgres administrator satisfies that requirement without
-- delegating Auth-schema access or BYPASSRLS to the collector login.
begin;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'sherlock_audit_source') then
    create role sherlock_audit_source nologin;
  end if;
end $$;
-- Owner permissions are intentional: expose only login facts through a private
-- security-barrier view, never the provider's payload or account table.
do $$ declare ip_expression text; begin
  ip_expression := case when exists (
    select 1 from information_schema.columns where table_schema = 'auth'
      and table_name = 'audit_log_entries' and column_name = 'ip_address'
  ) then 'ip_address::text' else 'null::text' end;
  execute format($view$
    create or replace view private.login_audit_source
      with (security_barrier = true, security_invoker = false) as
    select id, created_at, payload ->> 'action' as action,
      payload ->> 'actor_id' as actor_id, payload ->> 'user_agent' as user_agent,
      %s as ip_address
    from auth.audit_log_entries where payload ->> 'action' = 'login'
  $view$, ip_expression);
end $$;
revoke all on private.login_audit_source from public, anon, authenticated;
grant usage on schema private to sherlock_audit_source;
grant select on private.login_audit_source to sherlock_audit_source;

-- Remove the previous direct column grants when upgrading an existing setup.
revoke select (id, created_at, payload) on auth.audit_log_entries from sherlock_audit_source;
do $$ begin
  if exists (select 1 from information_schema.columns where table_schema = 'auth'
      and table_name = 'audit_log_entries' and column_name = 'ip_address') then
    revoke select (ip_address) on auth.audit_log_entries from sherlock_audit_source;
  end if;
end $$;
commit;
