begin;
-- Health metadata only. No new browser grants, login roles, or credentials.
alter table private.collection_state
  add column failure_status text not null default 'not_configured'
    check (failure_status in ('not_configured','ready','partial','error')),
  add column failure_checked_at timestamptz,
  add column failure_window_start timestamptz,
  add column failure_window_end timestamptz,
  add column failure_last_success_at timestamptz,
  add column failure_seen integer not null default 0 check(failure_seen between 0 and 10000000);

create function private.record_failure_collection(p_run uuid,p_status text,
  p_start timestamptz,p_end timestamptz,p_seen integer) returns boolean
language plpgsql security definer set search_path='' as $$
begin
  if p_run is null or p_status is null or p_seen is null
    or p_status not in ('not_configured','ready','partial','error')
    or p_seen not between 0 and 10000000
    or (p_status in ('ready','partial') and (p_start is null or p_end is null
      or p_start >= p_end or p_end > clock_timestamp()+interval '5 minutes'
      or p_start < clock_timestamp()-interval '2 hours'
      or p_end-p_start > interval '61 minutes')) then
    raise exception 'Invalid failure collection status' using errcode='22023';
  end if;
  update private.collection_state set failure_status=p_status,
    failure_checked_at=clock_timestamp(),failure_window_start=p_start,failure_window_end=p_end,
    failure_seen=p_seen,
    failure_last_success_at=case when p_status='ready' then clock_timestamp()
      else failure_last_success_at end
    where singleton and status='running' and run_id=p_run and lease_until>clock_timestamp();
  return found;
end $$;
revoke all on function private.record_failure_collection(uuid,text,timestamptz,timestamptz,integer)
  from public,anon,authenticated,sherlock_reader,sherlock_worker,sherlock_retention;
grant execute on function private.record_failure_collection(uuid,text,timestamptz,timestamptz,integer)
  to sherlock_ingest;
commit;
