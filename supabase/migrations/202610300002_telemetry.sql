begin;

-- Group roles have no passwords or login rights. Grant only the required group
-- to dedicated server login roles; never grant them to browser/PostgREST roles.
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'sherlock_ingest') then
    create role sherlock_ingest nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'sherlock_reader') then
    create role sherlock_reader nologin;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'sherlock_retention') then
    create role sherlock_retention nologin;
  end if;
end $$;

create table private.security_events (
  id uuid primary key default gen_random_uuid(),
  schema_version smallint not null default 1 check (schema_version = 1),
  source text not null check (source in ('supabase_audit', 'trusted_auth_adapter')),
  source_event_id uuid not null,
  occurred_at timestamptz not null,
  received_at timestamptz not null default clock_timestamp(),
  event_type text not null default 'login' check (event_type = 'login'),
  outcome text not null check (outcome in ('success', 'failure')),
  user_id uuid,
  account_key text check (account_key ~ '^[a-f0-9]{64}$'),
  source_ip inet,
  user_agent text check (char_length(user_agent) <= 512),
  processing_status text not null default 'pending' check (processing_status = 'pending'),
  payload_digest text not null check (payload_digest ~ '^[a-f0-9]{64}$'),
  unique (source, source_event_id)
);
comment on table private.security_events is
  'Trusted, allowlisted login facts. No passwords, tokens, raw emails, or provider payloads.';
-- IDs deliberately do not reference auth.users: historical events may refer to
-- deleted accounts. Apply the documented retention/deletion procedure.
create index security_events_time_idx on private.security_events (occurred_at desc, id desc);
create index security_events_user_time_idx on private.security_events (user_id, occurred_at, id);
create index security_events_source_time_idx on private.security_events (source_ip, occurred_at, id);
create index security_events_pending_idx on private.security_events (occurred_at, id)
  where processing_status = 'pending';

alter table private.security_events enable row level security;
revoke all on private.security_events from public, anon, authenticated;
grant usage on schema private to sherlock_ingest, sherlock_reader, sherlock_retention;
grant select, insert on private.security_events to sherlock_ingest;
grant select on private.security_events to sherlock_reader;
grant select, delete on private.security_events to sherlock_retention;
create policy events_ingest_insert on private.security_events for insert to sherlock_ingest
  with check (true);
create policy events_ingest_dedupe on private.security_events for select to sherlock_ingest
  using (true);
create policy events_server_read on private.security_events for select to sherlock_reader
  using (true);
create policy events_retention_read on private.security_events for select to sherlock_retention
  using (true);
create policy events_retention_delete on private.security_events for delete to sherlock_retention
  using (true);

commit;
