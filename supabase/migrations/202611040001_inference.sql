begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'sherlock_worker') then
    create role sherlock_worker nologin;
  end if;
end $$;

create table private.model_versions (
  id text primary key check (id ~ '^[a-f0-9]{64}$'),
  artifact_label text not null check (length(artifact_label) between 1 and 80),
  weights_digest text not null check (weights_digest ~ '^[a-f0-9]{64}$'),
  config_digest text not null check (config_digest ~ '^[a-f0-9]{64}$'),
  schema_digest text not null check (schema_digest ~ '^[a-f0-9]{64}$'),
  feature_version text not null check (feature_version = 'login-history-v1'),
  ml_threshold double precision not null check (ml_threshold >= 0 and ml_threshold <= 1),
  rule_threshold double precision not null check (rule_threshold >= 0 and rule_threshold < 'Infinity'),
  mode text not null default 'shadow' check (mode = 'shadow'),
  created_at timestamptz not null default clock_timestamp()
);

create table private.scoring_jobs (
  event_id uuid primary key references private.security_events(id) on delete cascade,
  state text not null default 'pending' check (state in ('pending','processing','processed','failed')),
  attempts smallint not null default 0 check (attempts between 0 and 5),
  next_attempt_at timestamptz not null default clock_timestamp(),
  lease_token uuid,
  lease_expires_at timestamptz,
  history_as_of timestamptz,
  model_version_id text references private.model_versions(id),
  last_error text check (last_error in ('scoring_failed','history_limit','lease_exhausted')),
  check ((state = 'processing') = (lease_token is not null and lease_expires_at is not null))
);
create index scoring_jobs_ready_idx on private.scoring_jobs (next_attempt_at, event_id)
  where state = 'pending';
create index scoring_jobs_lease_idx on private.scoring_jobs (lease_expires_at)
  where state = 'processing';
create index security_events_account_key_time_idx
  on private.security_events (account_key, occurred_at, id) where user_id is null;

create table private.detection_results (
  event_id uuid primary key references private.security_events(id) on delete cascade,
  model_version_id text not null references private.model_versions(id),
  feature_version text not null check (feature_version = 'login-history-v1'),
  features jsonb not null check (jsonb_typeof(features) = 'object' and pg_column_size(features) <= 8192),
  history_as_of timestamptz not null,
  ml_score double precision not null check (ml_score >= 0 and ml_score <= 1),
  rule_score double precision not null check (rule_score >= 0 and rule_score < 'Infinity'),
  flagged boolean not null,
  signals text[] not null,
  context_warnings text[] not null,
  scored_at timestamptz not null default clock_timestamp()
);
create index detection_results_time_idx on private.detection_results (scored_at desc, event_id desc);

create table private.incidents (
  id uuid primary key default gen_random_uuid(),
  model_version_id text not null references private.model_versions(id),
  entity_type text not null check (entity_type in ('account','source','event')),
  entity_key text not null check (length(entity_key) between 1 and 128),
  window_start timestamptz not null,
  first_seen timestamptz not null,
  last_seen timestamptz not null,
  created_at timestamptz not null default clock_timestamp(),
  unique (model_version_id, entity_type, entity_key, window_start)
);
create table private.incident_events (
  event_id uuid primary key references private.detection_results(event_id) on delete cascade,
  incident_id uuid not null references private.incidents(id) on delete cascade
);
create index incident_events_incident_idx on private.incident_events (incident_id, event_id);
create index incidents_time_idx on private.incidents (last_seen desc, id desc);

create table private.scoring_workers (
  id uuid primary key,
  model_version_id text references private.model_versions(id),
  status text not null check (status in ('ready','model_unavailable','stopped')),
  last_seen timestamptz not null default clock_timestamp()
);

-- Only these narrow SECURITY DEFINER functions may mutate worker-owned state.
-- Fixed empty search paths and qualified relations avoid caller-controlled objects.
create function private.enqueue_scoring_job() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  insert into private.scoring_jobs(event_id) values (new.id) on conflict do nothing;
  return new;
end $$;
create trigger enqueue_scoring_job after insert on private.security_events
  for each row execute function private.enqueue_scoring_job();
insert into private.scoring_jobs(event_id) select id from private.security_events;

create function private.register_scoring_model(
  version_id text, label text, weights text, config_hash text, schema_hash text,
  feature_schema text, ml_cutoff double precision, rule_cutoff double precision
) returns void language plpgsql security definer set search_path = '' as $$
begin
  insert into private.model_versions
    (id, artifact_label, weights_digest, config_digest, schema_digest, feature_version,
     ml_threshold, rule_threshold)
  values (version_id,label,weights,config_hash,schema_hash,feature_schema,ml_cutoff,rule_cutoff)
  on conflict do nothing;
  if not exists (select 1 from private.model_versions m where m.id = version_id
    and m.artifact_label = label and m.weights_digest = weights and m.config_digest = config_hash
    and m.schema_digest = schema_hash and m.feature_version = feature_schema
    and m.ml_threshold = ml_cutoff and m.rule_threshold = rule_cutoff) then
    raise exception 'Model version conflict' using errcode = '23514';
  end if;
end $$;

create function private.claim_scoring_job(version_id text, retention_days integer, lease_seconds integer)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare claimed private.scoring_jobs; facts private.security_events;
begin
  if retention_days not between 1 and 365 or lease_seconds not between 10 and 900 then
    raise exception 'Invalid worker bounds' using errcode = '22023';
  end if;
  if not exists (select 1 from private.model_versions where id = version_id) then
    raise exception 'Model not registered' using errcode = '23503';
  end if;
  -- A worker killed on its final attempt must not leave a permanently leased job.
  with expired as (
    select event_id from private.scoring_jobs where state = 'processing' and attempts >= 5
      and lease_expires_at <= clock_timestamp() order by event_id limit 100
      for update skip locked
  ) update private.scoring_jobs j set state = 'failed', lease_token = null,
    lease_expires_at = null, last_error = 'lease_exhausted'
    from expired where j.event_id = expired.event_id;

  select j.* into claimed from private.scoring_jobs j
    join private.security_events e on e.id = j.event_id
    where e.occurred_at > clock_timestamp() - make_interval(days => retention_days)
      and e.occurred_at <= clock_timestamp() and j.attempts < 5
      and ((j.state = 'pending' and j.next_attempt_at <= clock_timestamp())
        or (j.state = 'processing' and j.lease_expires_at <= clock_timestamp()))
    order by e.occurred_at, e.id for update of j skip locked limit 1;
  if not found then return null; end if;
  update private.scoring_jobs set state = 'processing', attempts = attempts + 1,
    lease_token = gen_random_uuid(), lease_expires_at = clock_timestamp() + make_interval(secs => lease_seconds),
    history_as_of = clock_timestamp(), model_version_id = version_id, last_error = null
    where event_id = claimed.event_id returning * into claimed;
  select * into facts from private.security_events where id = claimed.event_id;
  return jsonb_build_object('job', to_jsonb(claimed), 'event',
    to_jsonb(facts) || jsonb_build_object('source_ip',host(facts.source_ip)));
end $$;

create function private.fail_scoring_job(job_id uuid, token uuid, error_code text)
returns boolean language plpgsql security definer set search_path = '' as $$
begin
  if error_code not in ('scoring_failed','history_limit') then
    raise exception 'Invalid failure code' using errcode = '22023';
  end if;
  update private.scoring_jobs set state = case when attempts >= 5 then 'failed' else 'pending' end,
    next_attempt_at = clock_timestamp() + make_interval(secs => least(300,5 * power(2,attempts)::integer)),
    lease_token = null, lease_expires_at = null, last_error = error_code
    where event_id = job_id and state = 'processing' and lease_token = token
      and lease_expires_at > clock_timestamp();
  return found;
end $$;

create function private.complete_scoring_job(
  job_id uuid, token uuid, snapshot jsonb, anomaly double precision, rule_risk double precision,
  evidence text[], warnings text[]
) returns boolean language plpgsql security definer set search_path = '' as $$
declare job private.scoring_jobs; model private.model_versions; facts private.security_events;
  is_alert boolean; incident_id uuid; kind text; key text; bucket timestamptz;
  expected text[] := array['current_failure','account_failures_15m','account_attempts_15m',
    'source_attempts_5m','source_accounts_5m','source_failure_ratio_5m','account_history_30d',
    'account_successes_30d','browser_novel','hour_deviation','seconds_since_previous','has_previous',
    'account_missing','source_missing','browser_missing'];
begin
  select * into job from private.scoring_jobs where event_id = job_id and state = 'processing'
    and lease_token = token and lease_expires_at > clock_timestamp() for update;
  if not found then return false; end if;
  if jsonb_typeof(snapshot) <> 'object' or pg_column_size(snapshot) > 8192
    or (select count(*) from jsonb_object_keys(snapshot)) <> cardinality(expected)
    or not expected <@ array(select jsonb_object_keys(snapshot))
    or exists (select 1 from jsonb_each(snapshot) v where jsonb_typeof(v.value) <> 'number') then
    raise exception 'Invalid feature snapshot' using errcode = '23514';
  end if;
  if evidence is null or warnings is null or array_position(evidence,null) is not null
    or array_position(warnings,null) is not null
    or not evidence <@ array['ml_outlier','account_failure_burst','source_attempt_burst',
      'source_account_spread','unfamiliar_browser_and_hour']::text[]
    or not warnings <@ array['missing_account','missing_source_ip','missing_browser','cold_start',
      'limited_account_history','truncated_retention_history']::text[] then
    raise exception 'Invalid scoring evidence' using errcode = '23514';
  end if;
  select * into model from private.model_versions where id = job.model_version_id;
  select * into facts from private.security_events where id = job_id;
  is_alert := anomaly > model.ml_threshold or rule_risk > model.rule_threshold;
  insert into private.detection_results(event_id,model_version_id,feature_version,features,
    history_as_of,ml_score,rule_score,flagged,signals,context_warnings)
    values (job_id,model.id,model.feature_version,snapshot,job.history_as_of,anomaly,rule_risk,
      is_alert,evidence,warnings);
  if is_alert then
    -- Source bursts/sprays group across accounts; otherwise prefer the account.
    if facts.source_ip is not null and evidence && array['source_attempt_burst','source_account_spread'] then
      kind := 'source'; key := host(facts.source_ip);
    elsif facts.user_id is not null or facts.account_key is not null then
      kind := 'account'; key := case when facts.user_id is not null then 'user:' || facts.user_id::text
        else 'key:' || facts.account_key end;
    elsif facts.source_ip is not null then kind := 'source'; key := host(facts.source_ip);
    else kind := 'event'; key := facts.id::text; end if;
    bucket := to_timestamp(floor(extract(epoch from facts.occurred_at) / 900) * 900);
    insert into private.incidents(model_version_id,entity_type,entity_key,window_start,first_seen,last_seen)
      values(model.id,kind,key,bucket,facts.occurred_at,facts.occurred_at)
      on conflict(model_version_id,entity_type,entity_key,window_start) do update
        set first_seen = least(private.incidents.first_seen,excluded.first_seen),
          last_seen = greatest(private.incidents.last_seen,excluded.last_seen)
      returning id into incident_id;
    insert into private.incident_events(event_id,incident_id) values(job_id,incident_id);
  end if;
  update private.scoring_jobs set state = 'processed', lease_token = null, lease_expires_at = null,
    last_error = null where event_id = job_id;
  return true;
end $$;

create function private.scoring_heartbeat(worker_id uuid, version_id text, worker_status text)
returns void language sql security definer set search_path = '' as $$
  insert into private.scoring_workers(id,model_version_id,status)
  values(worker_id,version_id,worker_status) on conflict(id) do update
    set model_version_id = excluded.model_version_id, status = excluded.status,
      last_seen = clock_timestamp();
$$;

create function private.cleanup_empty_incident() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  delete from private.incidents i where i.id = old.incident_id
    and not exists (select 1 from private.incident_events where incident_id = i.id);
  update private.incidents i set first_seen = bounds.first_seen, last_seen = bounds.last_seen
    from (select min(e.occurred_at) as first_seen, max(e.occurred_at) as last_seen
      from private.incident_events ie join private.security_events e on e.id = ie.event_id
      where ie.incident_id = old.incident_id) bounds
    where i.id = old.incident_id and bounds.first_seen is not null;
  return old;
end $$;
create trigger cleanup_empty_incident after delete on private.incident_events
  for each row execute function private.cleanup_empty_incident();

-- Existing event facts and their grants are unchanged. Worker access is separate.
grant usage on schema private to sherlock_worker;
grant select on private.security_events to sherlock_worker;
create policy events_worker_read on private.security_events for select to sherlock_worker using (true);
do $$ declare relation text; begin
  foreach relation in array array['model_versions','scoring_jobs','detection_results','incidents',
    'incident_events','scoring_workers'] loop
    execute format('alter table private.%I enable row level security', relation);
    execute format('revoke all on private.%I from public, anon, authenticated, sherlock_worker', relation);
    execute format('grant select on private.%I to sherlock_reader', relation);
    execute format('create policy %I on private.%I for select to sherlock_reader using (true)',
      relation || '_server_read', relation);
  end loop;
end $$;
revoke all on function private.enqueue_scoring_job() from public, anon, authenticated;
revoke all on function private.cleanup_empty_incident() from public, anon, authenticated;
revoke all on function private.register_scoring_model(text,text,text,text,text,text,double precision,double precision)
  from public, anon, authenticated;
revoke all on function private.claim_scoring_job(text,integer,integer) from public, anon, authenticated;
revoke all on function private.fail_scoring_job(uuid,uuid,text) from public, anon, authenticated;
revoke all on function private.complete_scoring_job(uuid,uuid,jsonb,double precision,double precision,text[],text[])
  from public, anon, authenticated;
revoke all on function private.scoring_heartbeat(uuid,text,text) from public, anon, authenticated;
grant execute on function private.register_scoring_model(text,text,text,text,text,text,double precision,double precision),
  private.claim_scoring_job(text,integer,integer), private.fail_scoring_job(uuid,uuid,text),
  private.complete_scoring_job(uuid,uuid,jsonb,double precision,double precision,text[],text[]),
  private.scoring_heartbeat(uuid,text,text) to sherlock_worker;

commit;
