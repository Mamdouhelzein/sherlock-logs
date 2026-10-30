begin;

create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '' check (char_length(display_name) <= 80),
  created_at timestamptz not null default now()
);
alter table public.profiles enable row level security;
revoke all on public.profiles from public, anon, authenticated;
grant select on public.profiles to authenticated;
grant update (display_name) on public.profiles to authenticated;

create policy profiles_read_self on public.profiles
  for select to authenticated using ((select auth.uid()) = id);
create policy profiles_update_self on public.profiles
  for update to authenticated
  using ((select auth.uid()) = id) with check ((select auth.uid()) = id);

-- Never grant browser roles access to this table or expose the private schema.
create table private.user_roles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  role text not null check (role in ('member', 'admin')),
  updated_at timestamptz not null default now()
);
alter table private.user_roles enable row level security;
revoke all on private.user_roles from public, anon, authenticated;

create function private.create_profile()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, left(coalesce(new.raw_user_meta_data ->> 'display_name', ''), 80));
  return new;
end;
$$;
revoke all on function private.create_profile() from public, anon, authenticated;
create trigger on_auth_user_created after insert on auth.users
  for each row execute function private.create_profile();

-- Include users created before the migration. Roles default to member by absence.
insert into public.profiles (id, display_name)
select id, left(coalesce(raw_user_meta_data ->> 'display_name', ''), 80)
from auth.users on conflict (id) do nothing;

-- Deliberately callable over the Data API, but only for the authenticated caller.
-- No parameters, no dynamic SQL, no metadata-based privileges.
create function public.current_user_role()
returns text language sql stable security definer set search_path = '' as $$
  select case when (select auth.uid()) is null then null else
    coalesce((select role from private.user_roles where user_id = (select auth.uid())), 'member')
  end;
$$;
revoke all on function public.current_user_role() from public, anon, authenticated;
grant execute on function public.current_user_role() to authenticated;

commit;
