"""Restricted fixture operator for real browser tests; never operates on owner accounts."""

import argparse
import os
import re
import sys
from threading import Event

from free_auth import ROOT, configuration, owner_connection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["admin", "member"])
    parser.add_argument("email")
    args = parser.parse_args()
    if os.environ.get("TEST_FREE_AUTH") != "1" or not re.fullmatch(
        r"browser-[a-f0-9-]{36}@example\.test", args.email
    ):
        parser.error("Only explicit local browser fixtures are supported")
    values = configuration()
    with owner_connection(values) as c:
        row = c.execute(
            "select id from auth.users where email=%s and email_confirmed_at is not null",
            (args.email,),
        ).fetchone()
        if row is None:
            raise ValueError("Confirmed fixture not found")
        if args.action == "admin":
            c.execute(
                "insert into private.user_roles(user_id,role) values(%s,'admin') "
                "on conflict(user_id) do update set role='admin'",
                (row[0],),
            )
        else:
            c.execute("delete from private.user_roles where user_id=%s", (row[0],))
    if args.action == "admin":
        sys.path.insert(0, str(ROOT / "backend/src"))
        from sherlock_api.telemetry.scheduler import Collector, CollectorSettings

        collector = Collector(
            CollectorSettings(
                _env_file=None, **{key.lower(): value for key, value in values.items()}
            )
        )
        try:
            result = collector.cycle(Event())
            if result["status"] not in {"ready", "waiting"}:
                raise ValueError("Fixture collection did not complete")
        finally:
            collector.stop()
    print("Local browser fixture updated.")


if __name__ == "__main__":
    main()
