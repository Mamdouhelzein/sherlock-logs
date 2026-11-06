begin;
-- Fixed projection under owner rights; the audit login has no Auth account,
-- guard-state, hook execution or underlying journal privileges.
create or replace view private.password_rejection_source
  with(security_barrier=true,security_invoker=false) as
  select id,created_at,user_id,reason from auth_guard.password_rejections;
revoke all on private.password_rejection_source from public,anon,authenticated;
grant select on private.password_rejection_source to sherlock_audit_source;
commit;
