begin;
-- Shared event contract; this does not enable a hook on hosted Supabase.
alter table private.security_events drop constraint security_events_source_check;
alter table private.security_events add constraint security_events_source_check
  check(source in ('supabase_audit','trusted_auth_adapter','self_hosted_guard'));
alter table private.security_events add column rejection_reason text
  check(rejection_reason in ('invalid_password','cooldown_rejected'));
alter table private.security_events add constraint rejection_context_check
  check(rejection_reason is null or (source='self_hosted_guard' and outcome='failure'));
alter table private.collection_state add column failure_source_kind text not null default 'provider_logs'
  check(failure_source_kind in ('provider_logs','self_hosted_guard'));

create function private.record_failure_collection(p_run uuid,p_status text,
  p_start timestamptz,p_end timestamptz,p_seen integer,p_source text) returns boolean
language plpgsql security definer set search_path='' as $$
begin
  if p_run is null or p_status is null or p_seen is null or p_source is null
    or p_source not in ('provider_logs','self_hosted_guard')
    or p_status not in ('not_configured','ready','partial','error')
    or p_seen not between 0 and 10000000
    or (p_status in ('ready','partial') and (p_start is null or p_end is null
      or p_start >= p_end or p_end > clock_timestamp()+interval '5 minutes'
      or (p_source='provider_logs' and (p_start < clock_timestamp()-interval '2 hours'
        or p_end-p_start > interval '61 minutes'))
      or (p_source='self_hosted_guard' and p_end-p_start > interval '366 days'))) then
    raise exception 'Invalid failure collection status' using errcode='22023';
  end if;
  update private.collection_state set failure_status=p_status,failure_source_kind=p_source,
    failure_checked_at=clock_timestamp(),failure_window_start=p_start,failure_window_end=p_end,
    failure_seen=p_seen,
    failure_last_success_at=case when p_status='ready' then clock_timestamp()
      else failure_last_success_at end
    where singleton and status='running' and run_id=p_run and lease_until>clock_timestamp();
  return found;
end $$;
revoke all on function private.record_failure_collection(uuid,text,timestamptz,timestamptz,integer,text)
  from public,anon,authenticated,sherlock_reader,sherlock_worker,sherlock_retention;
grant execute on function private.record_failure_collection(uuid,text,timestamptz,timestamptz,integer,text)
  to sherlock_ingest;
commit;
