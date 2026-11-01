begin;
do $$ begin
  assert not has_schema_privilege('anon', 'private', 'USAGE');
  assert not has_schema_privilege('authenticated', 'private', 'USAGE');
  assert not has_table_privilege('authenticated', 'private.security_events', 'SELECT');
  assert not has_table_privilege('authenticated', 'private.security_events', 'INSERT');
  assert not has_table_privilege('sherlock_ingest', 'private.security_events', 'DELETE');
  assert not has_table_privilege('sherlock_reader', 'private.security_events', 'INSERT');
  assert not has_table_privilege('sherlock_retention', 'private.security_events', 'INSERT');
  assert not has_table_privilege('sherlock_audit_source', 'auth.users', 'SELECT');
  assert not has_table_privilege('anon', 'private.login_audit_source', 'SELECT');
  assert not has_table_privilege('authenticated', 'private.login_audit_source', 'SELECT');
  assert not has_table_privilege('sherlock_reader', 'private.login_audit_source', 'SELECT');
end $$;

set local role sherlock_ingest;
insert into private.security_events (source, source_event_id, occurred_at, outcome, payload_digest)
values ('trusted_auth_adapter', '00000000-0000-4000-8000-000000000099', now(), 'failure', repeat('a',64));
insert into private.security_events (source, source_event_id, occurred_at, outcome, payload_digest)
values ('trusted_auth_adapter', '00000000-0000-4000-8000-000000000099', now(), 'failure', repeat('a',64))
on conflict (source, source_event_id) do nothing returning id;
do $$ begin
  assert (select count(*) from private.security_events) = 1;
  assert (select processing_status from private.security_events) = 'pending';
  begin
    update private.security_events set outcome = 'success';
    raise exception 'Ingest role updated immutable event facts';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
set local role sherlock_reader;
do $$ begin assert (select count(*) from private.security_events) = 1; end $$;
reset role;
set local role authenticated;
do $$ begin
  begin
    perform * from private.security_events;
    raise exception 'Browser read telemetry';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;
insert into auth.audit_log_entries (id, created_at, payload)
values ('00000000-0000-4000-8000-000000000098', now(),
  '{"action":"login","email":"private@example.test","token":"never-expose"}'),
  ('00000000-0000-4000-8000-000000000097', now(), '{"action":"token_refreshed"}');
set local role sherlock_audit_source;
do $$ begin
  assert (select count(id) from private.login_audit_source
    where id = '00000000-0000-4000-8000-000000000098') = 1,
    'Audit reader cannot see rows through RLS';
  assert not exists (select 1 from private.login_audit_source
    where id = '00000000-0000-4000-8000-000000000097');
  assert (select count(*) from information_schema.columns
    where table_schema = 'private' and table_name = 'login_audit_source') = 6;
  assert not has_table_privilege(current_user, 'private.login_audit_source', 'INSERT');
  assert not has_table_privilege(current_user, 'private.login_audit_source', 'UPDATE');
  assert not has_table_privilege(current_user, 'private.login_audit_source', 'DELETE');
  begin
    perform payload from auth.audit_log_entries;
    raise exception 'Audit reader accessed raw provider payload';
  exception when insufficient_privilege then null;
  end;
end $$;
select id, created_at, action, actor_id, user_agent, ip_address from private.login_audit_source
where id = '00000000-0000-4000-8000-000000000098';
reset role;
set local role sherlock_retention;
delete from private.security_events;
reset role;
rollback;
