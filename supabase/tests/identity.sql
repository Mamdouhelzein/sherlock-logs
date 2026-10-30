-- Authorization integration checks on a migrated disposable PostgreSQL database.
-- Works after tests/bootstrap.sql in CI, or on a disposable Supabase development DB.
begin;
insert into auth.users(id, email, raw_user_meta_data) values
 ('00000000-0000-4000-8000-000000000001', 'one@example.test', '{"display_name":"One","role":"admin"}'),
 ('00000000-0000-4000-8000-000000000002', 'two@example.test', '{"display_name":"Two"}');

do $$ begin
  assert not has_schema_privilege('authenticated', 'private', 'USAGE');
  assert not has_table_privilege('authenticated', 'private.user_roles', 'INSERT');
  assert not has_function_privilege('anon', 'public.current_user_role()', 'EXECUTE');
  assert not has_table_privilege('anon', 'public.profiles', 'SELECT');
  assert not has_column_privilege('authenticated', 'public.profiles', 'id', 'UPDATE');
end $$;

set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated","user_metadata":{"role":"admin"}}';
do $$ begin
  assert (select count(*) from public.profiles) = 1, 'Profile isolation failed';
  assert (select display_name from public.profiles) = 'One', 'Profile trigger failed';
  assert public.current_user_role() = 'member', 'Metadata must not grant admin';
  update public.profiles set display_name = 'Changed' where id = auth.uid();
  assert (select display_name from public.profiles) = 'Changed', 'Self update failed';
  update public.profiles set display_name = 'Hijacked' where id = '00000000-0000-4000-8000-000000000002';
  assert not found, 'Cross-user write succeeded';
  begin
    insert into private.user_roles values (auth.uid(), 'admin', now());
    raise exception 'Self promotion succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    insert into public.profiles (id) values (auth.uid());
    raise exception 'Client profile insertion succeeded';
  exception when insufficient_privilege then null;
  end;
  begin
    delete from public.profiles where id = auth.uid();
    raise exception 'Client profile deletion succeeded';
  exception when insufficient_privilege then null;
  end;
end $$;
reset role;

insert into private.user_roles (user_id, role) values ('00000000-0000-4000-8000-000000000001', 'admin');
set local role authenticated;
do $$ begin assert public.current_user_role() = 'admin', 'Trusted promotion failed'; end $$;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000002","role":"authenticated"}';
do $$ begin
  assert public.current_user_role() = 'member', 'Role leaked between users';
  assert (select display_name from public.profiles) = 'Two', 'Other profile was changed';
end $$;
reset role;
delete from private.user_roles where user_id = '00000000-0000-4000-8000-000000000001';
set local role authenticated;
set local request.jwt.claims = '{"sub":"00000000-0000-4000-8000-000000000001","role":"authenticated"}';
do $$ begin assert public.current_user_role() = 'member', 'Role revocation failed'; end $$;
reset role;
rollback;
