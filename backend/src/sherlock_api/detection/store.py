"""Lease operations and repeatable-read context snapshots using a separate server role."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from psycopg import IsolationLevel
from psycopg.errors import SerializationFailure
from psycopg.types.json import Jsonb

from sherlock_api.telemetry.store import connect


@dataclass
class Claim:
    event: dict
    token: UUID
    history: list[dict]
    history_as_of: datetime
    history_overflow: bool
    retention_truncated: bool


class WorkerStore:
    def __init__(self, dsn: str, retention_days: int, lease_seconds: int, history_limit: int):
        self.dsn = dsn
        self.retention_days = retention_days
        self.lease_seconds = lease_seconds
        self.history_limit = history_limit

    def connection(self):
        return connect(self.dsn)

    def register(self, model):
        with self.connection() as connection:
            connection.execute(
                "select private.register_scoring_model(%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    model.version,
                    model.label,
                    model.digests["model.joblib"],
                    model.digests["experiment.json"],
                    model.digests["feature_schema.json"],
                    model.feature_version,
                    model.ml_threshold,
                    model.rule_threshold,
                ),
            )

    def heartbeat(self, worker_id: UUID, version: str | None, status: str):
        with self.connection() as connection:
            connection.execute(
                "select private.scoring_heartbeat(%s,%s,%s)", (worker_id, version, status)
            )

    def claim(self, version: str) -> Claim | None:
        for attempt in range(3):
            try:
                return self._claim(version)
            except SerializationFailure:
                if attempt == 2:
                    raise
        return None

    def _claim(self, version: str) -> Claim | None:
        with self.connection() as connection:
            connection.isolation_level = IsolationLevel.REPEATABLE_READ
            raw = connection.execute(
                "select private.claim_scoring_job(%s,%s,%s) as claim",
                (version, self.retention_days, self.lease_seconds),
            ).fetchone()["claim"]
            if raw is None:
                return None
            event = raw["event"]
            at = datetime.fromisoformat(event["occurred_at"])
            as_of = datetime.fromisoformat(raw["job"]["history_as_of"])
            # The transaction snapshot, not wall-clock query timing, fixes history.
            cutoff = max(at - timedelta(days=30), as_of - timedelta(days=self.retention_days))
            history = connection.execute(
                """select id::text, occurred_at, outcome, user_id::text, account_key,
                  host(source_ip) as source_ip, user_agent
                from private.security_events where occurred_at > %s
                  and (occurred_at,id) < (%s,%s)
                  and ((%s::uuid is not null and user_id = %s::uuid)
                    or (%s::uuid is null and %s::text is not null and user_id is null
                      and account_key = %s)
                    or (%s::inet is not null and source_ip = %s::inet
                      and occurred_at > %s))
                order by occurred_at,id limit %s""",
                (
                    cutoff,
                    at,
                    event["id"],
                    event["user_id"],
                    event["user_id"],
                    event["user_id"],
                    event["account_key"],
                    event["account_key"],
                    event["source_ip"],
                    event["source_ip"],
                    at - timedelta(minutes=5),
                    self.history_limit + 1,
                ),
            ).fetchall()
            # Commit the lease even on overflow, then fail it with a bounded retry.
            return Claim(
                event,
                UUID(raw["job"]["lease_token"]),
                history,
                as_of,
                len(history) > self.history_limit,
                cutoff > at - timedelta(days=30) + timedelta(minutes=5),
            )

    def complete(self, claim: Claim, result) -> bool:
        with self.connection() as connection:
            return connection.execute(
                "select private.complete_scoring_job(%s,%s,%s,%s,%s,%s,%s) as accepted",
                (
                    claim.event["id"],
                    claim.token,
                    Jsonb(result.features),
                    result.ml_score,
                    result.rule_score,
                    result.signals,
                    result.warnings,
                ),
            ).fetchone()["accepted"]

    def fail(self, claim: Claim, error_code: str) -> bool:
        with self.connection() as connection:
            return connection.execute(
                "select private.fail_scoring_job(%s,%s,%s) as accepted",
                (claim.event["id"], claim.token, error_code),
            ).fetchone()["accepted"]


class DetectionReader:
    def __init__(self, dsn: str, retention_days: int):
        self.dsn = dsn
        self.retention_days = retention_days

    def status(self) -> dict:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        with connect(self.dsn) as connection:
            queue = connection.execute(
                """select j.state,count(*) as count from private.scoring_jobs j
                  join private.security_events e on e.id = j.event_id
                  where e.occurred_at > %s group by j.state""",
                (cutoff,),
            ).fetchall()
            worker = connection.execute(
                """select w.status,w.last_seen,w.model_version_id,m.artifact_label
                  from private.scoring_workers w left join private.model_versions m
                    on m.id = w.model_version_id order by w.last_seen desc limit 1"""
            ).fetchone()
            result = connection.execute(
                """select count(*) as scored,count(*) filter(where r.flagged) as flagged
                  from private.detection_results r
                  join private.security_events e on e.id = r.event_id
                  where e.occurred_at > %s""",
                (cutoff,),
            ).fetchone()
        fresh = worker is not None and worker["last_seen"] > datetime.now(UTC) - timedelta(
            seconds=90
        )
        return {
            "mode": "shadow",
            "worker": worker,
            "worker_fresh": fresh,
            "worker_ready": fresh and worker["status"] == "ready",
            "queue": {row["state"]: row["count"] for row in queue},
            **result,
            "failed_login_coverage": "not_connected",
        }

    def event(self, event_id: UUID) -> dict | None:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        with connect(self.dsn) as connection:
            return connection.execute(
                """select e.id,e.occurred_at,e.received_at,e.source,e.outcome,e.user_id,
                  e.account_key,host(e.source_ip) as source_ip,e.user_agent,
                  j.state as job_state,j.attempts,j.last_error,
                  r.model_version_id,m.artifact_label,m.mode,r.features,r.feature_version,
                  r.ml_score,r.rule_score,m.ml_threshold,m.rule_threshold,r.flagged,r.signals,
                  r.context_warnings,r.history_as_of,r.scored_at
                from private.security_events e left join private.scoring_jobs j on j.event_id = e.id
                  left join private.detection_results r on r.event_id = e.id
                  left join private.model_versions m on m.id = r.model_version_id
                where e.id = %s and e.occurred_at > %s""",
                (event_id, cutoff),
            ).fetchone()

    def events(
        self, limit: int, before=None, *, flagged=None, outcome=None, user_id=None, account_key=None
    ) -> dict:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        conditions = ["e.occurred_at > %s"]
        values = [cutoff]
        for condition, parameters in (
            ("(e.occurred_at,e.id) < (%s,%s)", list(before) if before else []),
            ("r.flagged = %s", [flagged] if flagged is not None else []),
            ("e.outcome = %s", [outcome] if outcome else []),
            ("e.user_id = %s", [user_id] if user_id else []),
            ("e.user_id is null and e.account_key = %s", [account_key] if account_key else []),
        ):
            if parameters:
                conditions.append(condition)
                values.extend(parameters)
        with connect(self.dsn) as connection:
            rows = connection.execute(
                f"""select e.id,e.occurred_at,e.received_at,e.source,e.outcome,e.user_id,
                  e.account_key,host(e.source_ip) as source_ip,e.user_agent,
                  j.state as job_state,j.attempts,j.last_error,r.flagged,
                  r.ml_score,r.rule_score,r.signals,r.context_warnings,
                  r.model_version_id,m.artifact_label
                from private.security_events e left join private.scoring_jobs j on j.event_id=e.id
                  left join private.detection_results r on r.event_id=e.id
                  left join private.model_versions m on m.id=r.model_version_id
                where {" and ".join(conditions)}
                order by e.occurred_at desc,e.id desc limit %s""",
                (*values, limit + 1),
            ).fetchall()
        return {"rows": rows[:limit], "has_more": len(rows) > limit}

    def incidents(self, limit: int, before=None) -> dict:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        conditions = "and (i.last_seen,i.id) < (%s,%s)" if before else ""
        with connect(self.dsn) as connection:
            rows = connection.execute(
                f"""select i.id,i.model_version_id,m.artifact_label,i.entity_type,
                  i.first_seen,i.last_seen,i.window_start,count(ie.event_id) as event_count
                from private.incidents i join private.model_versions m on m.id = i.model_version_id
                  join private.incident_events ie on ie.incident_id = i.id
                  join private.security_events e on e.id = ie.event_id
                where e.occurred_at > %s {conditions}
                group by i.id,m.artifact_label order by i.last_seen desc,i.id desc limit %s""",
                (cutoff, *(before or ()), limit + 1),
            ).fetchall()
        return {"rows": rows[:limit], "has_more": len(rows) > limit}

    def incident(self, incident_id: UUID, limit: int, before=None) -> dict:
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        conditions = "and (e.occurred_at,e.id) < (%s,%s)" if before else ""
        with connect(self.dsn) as connection:
            rows = connection.execute(
                f"""select e.id,e.occurred_at,e.outcome,e.user_id,e.account_key,
                  host(e.source_ip) as source_ip,e.user_agent,r.model_version_id,r.feature_version,
                  r.features,r.ml_score,r.rule_score,r.flagged,r.signals,r.context_warnings,
                  r.history_as_of,r.scored_at
                from private.incident_events ie join private.security_events e on e.id = ie.event_id
                  join private.detection_results r on r.event_id = e.id
                where ie.incident_id = %s and e.occurred_at > %s {conditions}
                order by e.occurred_at desc,e.id desc limit %s""",
                (incident_id, cutoff, *(before or ()), limit + 1),
            ).fetchall()
        return {"rows": rows[:limit], "has_more": len(rows) > limit}
