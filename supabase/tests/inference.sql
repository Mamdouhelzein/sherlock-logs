-- Disposable test database only.
begin;
do $$ declare name text; signature text; begin
  foreach name in array array['model_versions','scoring_jobs','detection_results','incidents',
    'incident_events','scoring_workers'] loop
    assert not has_table_privilege('anon','private.' || name,'select');
    assert not has_table_privilege('authenticated','private.' || name,'select');
    assert has_table_privilege('sherlock_reader','private.' || name,'select');
    assert not has_table_privilege('sherlock_worker','private.' || name,'insert');
    assert not has_table_privilege('sherlock_worker','private.' || name,'update');
    assert not has_table_privilege('sherlock_reader','private.' || name,'delete');
  end loop;
  foreach signature in array array[
    'private.claim_scoring_job(text,integer,integer)',
    'private.fail_scoring_job(uuid,uuid,text)',
    'private.complete_scoring_job(uuid,uuid,jsonb,double precision,double precision,text[],text[])',
    'private.register_scoring_model(text,text,text,text,text,text,double precision,double precision)',
    'private.scoring_heartbeat(uuid,text,text)'
  ] loop
    assert has_function_privilege('sherlock_worker',signature,'execute');
    assert not has_function_privilege('anon',signature,'execute');
    assert not has_function_privilege('authenticated',signature,'execute');
    assert not has_function_privilege('sherlock_ingest',signature,'execute');
    assert not has_function_privilege('sherlock_reader',signature,'execute');
  end loop;
  assert has_table_privilege('sherlock_worker','private.security_events','select');
  assert not has_table_privilege('sherlock_worker','private.security_events','insert');
  assert not has_table_privilege('sherlock_worker','private.security_events','update');
  assert not has_table_privilege('sherlock_worker','auth.users','select');
end $$;
insert into private.security_events(id,source,source_event_id,occurred_at,outcome,payload_digest)
values ('11111111-0000-4000-8000-000000000001','trusted_auth_adapter',
  '11111111-0000-4000-8000-000000000001',clock_timestamp()-interval '1 minute','failure',repeat('f',64));
set local role sherlock_worker;
select private.register_scoring_model(repeat('a',64),'sql-fixture',repeat('b',64),repeat('c',64),
  repeat('d',64),'login-history-v1',0.5,0.6);
do $$ declare claim jsonb; snapshot jsonb; accepted boolean; begin
  claim := private.claim_scoring_job(repeat('a',64),30,60);
  assert claim is not null;
  snapshot := '{"current_failure":1,"account_failures_15m":0,"account_attempts_15m":0,
    "source_attempts_5m":0,"source_accounts_5m":0,"source_failure_ratio_5m":0,
    "account_history_30d":0,"account_successes_30d":0,"browser_novel":0,"hour_deviation":0,
    "seconds_since_previous":0,"has_previous":0,"account_missing":1,"source_missing":1,
    "browser_missing":1}'::jsonb;
  accepted := private.complete_scoring_job((claim->'event'->>'id')::uuid,
    (claim->'job'->>'lease_token')::uuid,snapshot,0.9,0,array['ml_outlier'],array['cold_start']);
  assert accepted;
  assert not private.complete_scoring_job((claim->'event'->>'id')::uuid,
    (claim->'job'->>'lease_token')::uuid,snapshot,0.9,0,array['ml_outlier'],array['cold_start']);
  begin
    update private.security_events set outcome='success';
    raise exception 'Worker changed original event facts';
  exception when insufficient_privilege then null; end;
end $$;
reset role;
do $$ begin
  assert (select count(*) from private.detection_results)=1;
  assert (select count(*) from private.incident_events)=1;
  assert (select state from private.scoring_jobs
    where event_id='11111111-0000-4000-8000-000000000001')='processed';
end $$;
rollback;
