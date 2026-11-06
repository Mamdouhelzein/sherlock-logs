begin;
-- Preserve the bounded completion contract, adding the explicit cooldown context.
create or replace function private.complete_scoring_job(
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
      'limited_account_history','truncated_retention_history','cooldown_rejection']::text[] then
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
commit;
