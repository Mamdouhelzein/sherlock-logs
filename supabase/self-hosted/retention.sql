-- Local realm only. Installation never enables deletion.
begin;
do $$ begin
  if not exists(select 1 from pg_roles where rolname='sherlock_local_cleanup') then
    create role sherlock_local_cleanup nologin;
  end if;
  if not exists(select 1 from pg_roles where rolname='sherlock_cleanup_owner') then
    create role sherlock_cleanup_owner nologin;
  end if;
end $$;
-- Keep each bounded provider-log batch indexable as history grows.
create index if not exists sherlock_audit_expiry_idx on auth.audit_log_entries(created_at,id);
create table if not exists private.local_retention_state (
  singleton boolean primary key default true check(singleton),
  last_attempt_at timestamptz,
  last_success_at timestamptz,
  next_run_at timestamptz,
  journal_deleted integer not null default 0 check(journal_deleted between 0 and 10000),
  audit_deleted integer not null default 0 check(audit_deleted between 0 and 10000),
  incidents_deleted integer not null default 0 check(incidents_deleted between 0 and 10000)
);
insert into private.local_retention_state(singleton) values(true) on conflict do nothing;
alter table private.local_retention_state enable row level security;
revoke all on private.local_retention_state from public,anon,authenticated,
  sherlock_ingest,sherlock_worker,sherlock_audit_source,sherlock_local_cleanup;
grant select on private.local_retention_state to sherlock_reader;
drop policy if exists local_retention_server_read on private.local_retention_state;
create policy local_retention_server_read on private.local_retention_state
  for select to sherlock_reader using(true);

-- The definer is not postgres: provider-owned audit triggers must never run as
-- a database superuser. Grant only the columns and metadata this routine needs.
grant usage on schema private,auth,auth_guard to sherlock_cleanup_owner;
grant select on private.retention_state,private.local_retention_state to sherlock_cleanup_owner;
grant update(status,last_started_at,last_finished_at,last_success_at,deleted,backlog,error_code)
  on private.retention_state to sherlock_cleanup_owner;
grant update(last_attempt_at,last_success_at,next_run_at,journal_deleted,audit_deleted,incidents_deleted)
  on private.local_retention_state to sherlock_cleanup_owner;
-- FOR UPDATE SKIP LOCKED requires UPDATE privilege; only the identifier column
-- is granted, with expired-row policies on protected source tables.
grant select(id,created_at),update(id),delete on auth.audit_log_entries,auth_guard.password_rejections
  to sherlock_cleanup_owner;
grant select(id,last_seen),update(id),delete on private.incidents to sherlock_cleanup_owner;
grant select(incident_id) on private.incident_events to sherlock_cleanup_owner;
grant execute on function private.run_retention_cleanup() to sherlock_cleanup_owner;
drop policy if exists cleanup_owner_read on private.retention_state;
create policy cleanup_owner_read on private.retention_state for select
  to sherlock_cleanup_owner using(true);
drop policy if exists cleanup_owner_update on private.retention_state;
create policy cleanup_owner_update on private.retention_state for update
  to sherlock_cleanup_owner using(true) with check(true);
drop policy if exists cleanup_owner_read on private.local_retention_state;
create policy cleanup_owner_read on private.local_retention_state for select
  to sherlock_cleanup_owner using(true);
drop policy if exists cleanup_owner_update on private.local_retention_state;
create policy cleanup_owner_update on private.local_retention_state for update
  to sherlock_cleanup_owner using(true) with check(true);
do $$ declare target text; begin
  foreach target in array array['auth.audit_log_entries','auth_guard.password_rejections'] loop
    execute 'drop policy if exists cleanup_owner_expired_read on '||target;
    execute 'create policy cleanup_owner_expired_read on '||target||
      ' for select to sherlock_cleanup_owner using(created_at<now()-interval ''30 days'')';
    execute 'drop policy if exists cleanup_owner_expired_delete on '||target;
    execute 'create policy cleanup_owner_expired_delete on '||target||
      ' for delete to sherlock_cleanup_owner using(created_at<now()-interval ''30 days'')';
    execute 'drop policy if exists cleanup_owner_expired_lock on '||target;
    execute 'create policy cleanup_owner_expired_lock on '||target||
      ' for update to sherlock_cleanup_owner using(created_at<now()-interval ''30 days'')'||
      ' with check(created_at<now()-interval ''30 days'')';
  end loop;
end $$;
drop policy if exists cleanup_owner_incident_read on private.incidents;
create policy cleanup_owner_incident_read on private.incidents for select
  to sherlock_cleanup_owner using(true);
drop policy if exists cleanup_owner_incident_delete on private.incidents;
create policy cleanup_owner_incident_delete on private.incidents for delete
  to sherlock_cleanup_owner using(not exists(select 1 from private.incident_events e
    where e.incident_id=private.incidents.id));
drop policy if exists cleanup_owner_incident_lock on private.incidents;
create policy cleanup_owner_incident_lock on private.incidents for update
  to sherlock_cleanup_owner using(not exists(select 1 from private.incident_events e
    where e.incident_id=private.incidents.id)) with check(not exists(
      select 1 from private.incident_events e where e.incident_id=private.incidents.id));
drop policy if exists cleanup_owner_memberships on private.incident_events;
create policy cleanup_owner_memberships on private.incident_events for select
  to sherlock_cleanup_owner using(true);

create or replace function private.run_local_retention_cleanup() returns jsonb
language plpgsql security definer set search_path='' set lock_timeout='2s' as $$
declare
  policy private.retention_state; timer private.local_retention_state;
  cutoff timestamptz; event_count integer:=0; journal_count integer:=0;
  audit_count integer:=0; incident_count integer:=0; n integer;
  remaining boolean; outcome text;
begin
  if not pg_try_advisory_xact_lock(78623412) then
    return jsonb_build_object('status','busy');
  end if;
  -- Share the existing event cleanup's lock so another owner cleanup cannot race.
  if not pg_try_advisory_xact_lock(78623411) then
    return jsonb_build_object('status','busy');
  end if;
  select * into strict policy from private.retention_state where singleton for update;
  if not policy.enabled then return jsonb_build_object('status','disabled'); end if;
  select * into strict timer from private.local_retention_state where singleton for update;
  if timer.next_run_at > clock_timestamp() then
    return jsonb_build_object('status','not_due');
  end if;
  cutoff:=clock_timestamp()-make_interval(days=>policy.keep_days);
  update private.local_retention_state set last_attempt_at=clock_timestamp() where singleton;
  begin
    event_count:=private.run_retention_cleanup();
    if (select status='error' from private.retention_state where singleton) then
      raise exception 'Event cleanup failed';
    end if;
    for iteration in 1..10 loop
      delete from auth_guard.password_rejections where id in (
        select id from auth_guard.password_rejections where created_at<cutoff
        order by created_at,id for update skip locked limit 1000
      );
      get diagnostics n=row_count; journal_count:=journal_count+n;
      exit when n<1000;
    end loop;
    for iteration in 1..10 loop
      delete from auth.audit_log_entries where id in (
        select id from auth.audit_log_entries where created_at<cutoff
        order by created_at,id for update skip locked limit 1000
      );
      get diagnostics n=row_count; audit_count:=audit_count+n;
      exit when n<1000;
    end loop;
    for iteration in 1..10 loop
      delete from private.incidents where id in (
        select i.id from private.incidents i where not exists(
          select 1 from private.incident_events e where e.incident_id=i.id)
        order by i.last_seen,i.id for update of i skip locked limit 1000
      );
      get diagnostics n=row_count; incident_count:=incident_count+n;
      exit when n<1000;
    end loop;
    remaining:=(select backlog from private.retention_state where singleton)
      or exists(select 1 from auth_guard.password_rejections where created_at<cutoff)
      or exists(select 1 from auth.audit_log_entries where created_at<cutoff)
      or exists(select 1 from private.incidents i where not exists(
        select 1 from private.incident_events e where e.incident_id=i.id));
    outcome:=case when remaining then 'partial' else 'ready' end;
    update private.retention_state set status=outcome,backlog=remaining,error_code=null,
      last_finished_at=clock_timestamp(),
      last_success_at=case when not remaining then clock_timestamp()
        else policy.last_success_at end where singleton;
    update private.local_retention_state set journal_deleted=journal_count,
      audit_deleted=audit_count,incidents_deleted=incident_count,
      last_success_at=case when not remaining then clock_timestamp() else timer.last_success_at end,
      next_run_at=clock_timestamp()+case when remaining then interval '1 minute'
        else interval '1 hour' end where singleton;
    return jsonb_build_object('status',outcome,'events_deleted',event_count,
      'journal_deleted',journal_count,'audit_deleted',audit_count,
      'incidents_deleted',incident_count);
  exception when others then
    -- Roll back this entire pass, including cascading results, before publishing failure.
    update private.retention_state set status='error',error_code='cleanup_failed',deleted=0,
      last_started_at=clock_timestamp(),last_finished_at=clock_timestamp(),backlog=true
      where singleton;
    update private.local_retention_state set journal_deleted=0,audit_deleted=0,
      incidents_deleted=0,next_run_at=clock_timestamp()+interval '1 minute' where singleton;
    return jsonb_build_object('status','error');
  end;
end $$;
alter function private.run_local_retention_cleanup() owner to sherlock_cleanup_owner;

create or replace function private.local_retention_healthy() returns boolean
language sql stable security definer set search_path='' as $$
  select r.enabled and r.status='ready' and not r.backlog and
    coalesce(l.last_success_at>now()-interval '2 hours',false)
  from private.retention_state r join private.local_retention_state l using(singleton)
  where r.singleton
$$;
revoke all on function private.run_local_retention_cleanup(),private.local_retention_healthy()
  from public,anon,authenticated,supabase_auth_admin,sherlock_ingest,sherlock_reader,
    sherlock_worker,sherlock_audit_source,sherlock_retention;
grant usage on schema private to sherlock_local_cleanup;
grant execute on function private.run_local_retention_cleanup(),private.local_retention_healthy()
  to sherlock_local_cleanup;
commit;
