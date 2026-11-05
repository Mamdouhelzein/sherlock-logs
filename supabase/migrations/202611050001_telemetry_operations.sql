begin;

create table private.collection_state (
  singleton boolean primary key default true check (singleton),
  run_id uuid,
  status text not null default 'idle' check (status in ('idle','running','ready','partial','error','stopped')),
  lease_until timestamptz,
  heartbeat_at timestamptz,
  started_at timestamptz,
  finished_at timestamptz,
  last_success_at timestamptz,
  last_full_scan_at timestamptz,
  last_full_retention_days integer,
  next_run_at timestamptz,
  interval_seconds integer not null default 30 check (interval_seconds between 10 and 900),
  retention_days integer not null default 30 check (retention_days between 1 and 365),
  scan_full boolean not null default true,
  counts jsonb not null default '{"scanned":0,"inserted":0,"duplicates":0,"rejected":0}',
  error_code text check (error_code in ('source_or_storage_unavailable','invalid_source','event_conflict','incomplete_scan')),
  check ((status = 'running') = (lease_until is not null))
);
insert into private.collection_state(singleton) values(true);
alter table private.collection_state enable row level security;
revoke all on private.collection_state from public,anon,authenticated,sherlock_ingest,sherlock_worker;
grant select on private.collection_state to sherlock_reader;
create policy collection_server_read on private.collection_state for select to sherlock_reader using (true);

-- Disabled until a trusted owner approves and installs the cleanup schedule.
create table private.retention_state (
  singleton boolean primary key default true check (singleton),
  enabled boolean not null default false,
  keep_days integer not null default 30 check (keep_days between 30 and 365),
  status text not null default 'disabled' check (status in ('disabled','ready','partial','error')),
  last_started_at timestamptz,
  last_finished_at timestamptz,
  last_success_at timestamptz,
  deleted integer not null default 0 check (deleted between 0 and 10000),
  backlog boolean not null default false,
  error_code text check (error_code = 'cleanup_failed')
);
insert into private.retention_state(singleton) values(true);
alter table private.retention_state enable row level security;
revoke all on private.retention_state from public,anon,authenticated,sherlock_ingest,sherlock_worker;
grant select on private.retention_state to sherlock_reader;
create policy retention_server_read on private.retention_state for select to sherlock_reader using (true);

create function private.begin_collection_run(p_run uuid,p_days integer,p_interval integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare current_state private.collection_state; full_scan boolean; begin
  if p_run is null or p_days is null or p_interval is null
    or p_days not between 1 and 365 or p_interval not between 10 and 900 then
    raise exception 'Invalid collection configuration' using errcode='22023';
  end if;
  if exists(select 1 from private.retention_state
    where singleton and enabled and p_days > keep_days) then
    raise exception 'Collection window exceeds active cleanup policy' using errcode='22023';
  end if;
  select * into current_state from private.collection_state where singleton for update;
  if (current_state.status='running' and current_state.lease_until > clock_timestamp())
    or (current_state.status <> 'stopped' and current_state.next_run_at > clock_timestamp()) then
    return null;
  end if;
  full_scan := current_state.last_full_scan_at is null
    or current_state.last_full_scan_at < clock_timestamp()-interval '6 hours'
    or coalesce(current_state.last_full_retention_days,0) <> p_days;
  update private.collection_state set run_id=p_run,status='running',started_at=clock_timestamp(),
    heartbeat_at=clock_timestamp(),lease_until=clock_timestamp()+interval '120 seconds',
    next_run_at=null,
    interval_seconds=p_interval,retention_days=p_days,scan_full=full_scan,error_code=null
    where singleton;
  return jsonb_build_object('run_id',p_run,'full_scan',full_scan);
end $$;

create function private.collection_progress(p_run uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
begin
  update private.collection_state set heartbeat_at=clock_timestamp(),
    lease_until=clock_timestamp()+interval '120 seconds'
    where singleton and status='running' and run_id=p_run and lease_until>clock_timestamp();
  return found;
end $$;

create function private.finish_collection_run(p_run uuid,p_status text,p_counts jsonb,p_error text,p_delay integer)
returns boolean language plpgsql security definer set search_path = '' as $$
declare expected text[] := array['scanned','inserted','duplicates','rejected']; begin
  if p_status is null or p_delay is null or p_counts is null
    or p_status not in ('ready','partial','error','stopped') or p_delay not between 10 and 900
    or jsonb_typeof(p_counts) <> 'object'
    or (select count(*) from jsonb_object_keys(p_counts)) <> 4
    or not expected <@ array(select jsonb_object_keys(p_counts))
    or exists(select 1 from jsonb_each(p_counts)
      where jsonb_typeof(value) <> 'number' or value::text !~ '^[0-9]{1,9}$')
    or (p_counts->>'scanned')::bigint <> (p_counts->>'inserted')::bigint
      + (p_counts->>'duplicates')::bigint + (p_counts->>'rejected')::bigint
    or (p_status='ready' and (p_error is not null or (p_counts->>'rejected')::integer <> 0))
    or (p_error is not null and p_error not in ('source_or_storage_unavailable','invalid_source','event_conflict','incomplete_scan')) then
    raise exception 'Invalid collection result' using errcode='22023';
  end if;
  update private.collection_state set status=p_status,counts=p_counts,error_code=p_error,
    heartbeat_at=clock_timestamp(),finished_at=clock_timestamp(),lease_until=null,
    last_success_at=case when p_status='ready' then clock_timestamp() else last_success_at end,
    last_full_scan_at=case when p_status='ready' and scan_full then started_at else last_full_scan_at end,
    last_full_retention_days=case when p_status='ready' and scan_full then retention_days
      else last_full_retention_days end,
    next_run_at=clock_timestamp()+make_interval(secs=>p_delay)
    where singleton and run_id=p_run and status='running' and lease_until>clock_timestamp();
  return found;
end $$;

create function private.stop_collection_run(p_run uuid) returns void
language plpgsql security definer set search_path = '' as $$
begin
  update private.collection_state set status='stopped',lease_until=null,heartbeat_at=clock_timestamp()
    where singleton and run_id=p_run;
end $$;

-- Owner/cron only: no runtime API, collector, worker, or browser can invoke deletion.
-- At most 10,000 expired event facts per call; related scoring data cascades.
create function private.run_retention_cleanup() returns integer
language plpgsql security definer set search_path = '' as $$
declare policy private.retention_state; cutoff timestamptz; removed integer:=0;
  batch integer; remaining boolean; begin
  if not pg_try_advisory_xact_lock(78623411) then return 0; end if;
  select * into policy from private.retention_state where singleton for update;
  if not policy.enabled then return 0; end if;
  cutoff := clock_timestamp()-make_interval(days=>policy.keep_days);
  update private.retention_state set last_started_at=clock_timestamp() where singleton;
  begin
    for iteration in 1..10 loop
      delete from private.security_events where id in (
        select id from private.security_events where occurred_at < cutoff
        order by occurred_at,id for update skip locked limit 1000
      );
      get diagnostics batch=row_count;
      removed:=removed+batch;
      exit when batch < 1000;
    end loop;
    select exists(select 1 from private.security_events where occurred_at<cutoff) into remaining;
    update private.retention_state set status=case when remaining then 'partial' else 'ready' end,
      deleted=removed,backlog=remaining,error_code=null,last_finished_at=clock_timestamp(),
      last_success_at=case when not remaining then clock_timestamp() else last_success_at end
      where singleton;
  exception when others then
    -- The nested block rolls back all event deletions before recording the failure.
    update private.retention_state set status='error',error_code='cleanup_failed',deleted=0,
      last_finished_at=clock_timestamp() where singleton;
    return 0;
  end;
  return removed;
end $$;

revoke all on function private.begin_collection_run(uuid,integer,integer),
  private.collection_progress(uuid),private.finish_collection_run(uuid,text,jsonb,text,integer),
  private.stop_collection_run(uuid),private.run_retention_cleanup()
  from public,anon,authenticated,sherlock_ingest,sherlock_reader,sherlock_worker,sherlock_retention;
grant execute on function private.begin_collection_run(uuid,integer,integer),
  private.collection_progress(uuid),private.finish_collection_run(uuid,text,jsonb,text,integer),
  private.stop_collection_run(uuid) to sherlock_ingest;
commit;
