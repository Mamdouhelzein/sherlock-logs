-- Self-hosted Auth only. Not in migrations: never implies hosted activation.
begin;

create schema if not exists auth_guard;
revoke all on schema auth_guard from public, anon, authenticated;
grant usage on schema auth_guard to supabase_auth_admin;

create table if not exists auth_guard.password_attempts (
  user_id uuid primary key references auth.users(id) on delete cascade,
  window_started_at timestamptz not null default clock_timestamp(),
  failures integer not null default 0 check (failures between 0 and 5),
  blocked_until timestamptz,
  updated_at timestamptz not null default clock_timestamp(),
  check (blocked_until is null or failures = 5)
);
alter table auth_guard.password_attempts enable row level security;
revoke all on auth_guard.password_attempts from public, anon, authenticated;
grant select, insert, update on auth_guard.password_attempts to supabase_auth_admin;
drop policy if exists auth_service_only on auth_guard.password_attempts;
create policy auth_service_only on auth_guard.password_attempts
  for all to supabase_auth_admin using (true) with check (true);

create or replace function auth_guard.check_password_attempt(event jsonb)
returns jsonb language plpgsql security invoker
set search_path = '' set lock_timeout = '500ms' as $$
declare
  account_id uuid;
  password_valid boolean;
  state auth_guard.password_attempts%rowtype;
  observed_at timestamptz;
  failure_count integer;
  window_start timestamptz;
begin
  if jsonb_typeof(event) is distinct from 'object'
    or jsonb_typeof(event->'user_id') is distinct from 'string'
    or jsonb_typeof(event->'valid') is distinct from 'boolean' then
    raise exception using errcode = '22023', message = 'Invalid password hook input';
  end if;
  begin
    account_id := (event->>'user_id')::uuid;
  exception when invalid_text_representation then
    raise exception using errcode = '22023', message = 'Invalid password hook input';
  end;
  password_valid := (event->>'valid')::boolean;

  -- The primary key also serializes concurrent first attempts for this account.
  insert into auth_guard.password_attempts(user_id) values(account_id)
    on conflict (user_id) do nothing;
  select * into strict state from auth_guard.password_attempts
    where user_id = account_id for update;
  observed_at := clock_timestamp();

  if state.blocked_until > observed_at then
    -- Fixed deadline: a hostile request cannot prolong this cooldown.
    return jsonb_build_object('decision', 'reject',
      'message', 'Invalid login credentials', 'should_logout_user', false);
  end if;

  if password_valid then
    update auth_guard.password_attempts set failures = 0, blocked_until = null,
      window_started_at = observed_at, updated_at = observed_at
      where user_id = account_id;
    return jsonb_build_object('decision', 'continue');
  end if;

  if state.blocked_until is not null
    or state.window_started_at + interval '15 minutes' <= observed_at then
    failure_count := 1;
    window_start := observed_at;
  else
    failure_count := state.failures + 1;
    window_start := state.window_started_at;
  end if;
  update auth_guard.password_attempts set failures = failure_count,
    window_started_at = window_start, updated_at = observed_at,
    blocked_until = case when failure_count >= 5
      then observed_at + interval '15 minutes' else null end
    where user_id = account_id;

  -- Invalid passwords below the threshold are still denied by Auth itself.
  if failure_count >= 5 then
    return jsonb_build_object('decision', 'reject',
      'message', 'Invalid login credentials', 'should_logout_user', false);
  end if;
  return jsonb_build_object('decision', 'continue');
end;
$$;
revoke all on function auth_guard.check_password_attempt(jsonb) from public, anon, authenticated;
grant execute on function auth_guard.check_password_attempt(jsonb) to supabase_auth_admin;

commit;
