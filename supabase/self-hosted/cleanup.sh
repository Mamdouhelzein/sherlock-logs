#!/bin/sh
# Only aggregate function results reach the bounded Docker log. Never print psql errors.
set -u
trap 'exit 0' TERM INT
while true; do
  if ! psql -X -qAt -v ON_ERROR_STOP=1 -c 'select private.run_local_retention_cleanup()' 2>/dev/null; then
    printf '%s\n' '{"status":"database_unavailable"}'
  fi
  sleep 60 &
  wait "$!"
done
