-- Trusted owner only, AFTER explicit approval of permanent 30-day event deletion.
-- Apply 202611050001_telemetry_operations.sql first. No credentials in this job.
begin;
create extension if not exists pg_cron with schema pg_catalog;
select cron.schedule('sherlock-retention-30-days','17 * * * *',
  'select private.run_retention_cleanup();');
update private.retention_state set enabled=true,keep_days=30,status='disabled'
  where singleton;
commit;
-- Run a bounded first cycle and inspect the private status. A recorded successful
-- run, not merely an installed schedule, establishes cleanup health.
select private.run_retention_cleanup() as deleted_expired_events;
select enabled,keep_days,status,deleted,backlog,last_success_at from private.retention_state;
select jobname,schedule,active from cron.job where jobname='sherlock-retention-30-days';
