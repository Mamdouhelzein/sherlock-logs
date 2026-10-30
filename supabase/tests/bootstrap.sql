-- Disposable vanilla PostgreSQL CI fixture. Never run against a Supabase project.
create role anon nologin;
create role authenticated nologin;
create schema auth;
create table auth.users (
  id uuid primary key,
  email text,
  raw_user_meta_data jsonb not null default '{}'
);
create table auth.audit_log_entries (
  id uuid primary key,
  created_at timestamptz,
  payload json,
  ip_address varchar(64) not null default ''
);
create function auth.uid() returns uuid language sql stable as $$
  select (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')::uuid;
$$;
grant usage on schema auth, public to authenticated, anon;
grant execute on function auth.uid() to authenticated, anon;
