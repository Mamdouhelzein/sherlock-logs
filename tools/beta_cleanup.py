"""Run the restricted self-hosted retention function; print aggregate counts only."""

import json
import os

import psycopg
from sherlock_api.deployment import database_url


def main():
    try:
        with psycopg.connect(
            database_url(os.environ, "CLEANUP_DATABASE_URL"), connect_timeout=10
        ) as c:
            c.execute("set local statement_timeout='60s'")
            result = c.execute(
                "select private.run_local_retention_cleanup()"
            ).fetchone()[0]
        print(json.dumps(result))
        return 0 if result["status"] in {"ready", "not_due", "busy"} else 2
    except (psycopg.Error, ValueError, OSError, KeyError, TypeError):
        print('{"status":"cleanup_unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
