import { useEffect, useRef, useState } from "react";
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  Activity,
  ArrowDown,
  ArrowRight,
  Check,
  ChevronRight,
  CircleAlert,
  Clock3,
  Fingerprint,
  FolderSearch,
  Layers3,
  ListFilter,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useAuth } from "../auth/AuthProvider";
import { AccessError } from "../lib/api";
import {
  detailSchema,
  eventSchema,
  incidentSchema,
  investigationRequest,
  operationsSchema,
  pageSchema,
  statusSchema,
  timelineEventSchema,
  type EventDetail,
  type Incident,
  type InvestigationEvent,
} from "./api";
import "./investigation.css";
import { OperationsHealth } from "./OperationsHealth";

const signals: Record<string, [string, string]> = {
  ml_outlier: [
    "Unusual behavior",
    "Isolation Forest placed this event beyond its calibrated alert threshold. This is not proof of compromise.",
  ],
  account_failure_burst: [
    "Repeated failures",
    "The recent failure count for this account exceeded the calibrated rule threshold.",
  ],
  source_attempt_burst: [
    "Source activity burst",
    "The recent attempt count from this source exceeded the calibrated rule threshold.",
  ],
  source_account_spread: [
    "Multiple accounts targeted",
    "This source attempted enough distinct accounts to exceed the calibrated rule threshold.",
  ],
  unfamiliar_browser_and_hour: [
    "Unfamiliar browser and time",
    "A successful login combined a new browser with an unusual hour relative to the available account history.",
  ],
};
const warnings: Record<string, string> = {
  missing_account: "No account identifier was available.",
  missing_source_ip: "The source did not provide an IP address.",
  missing_browser: "The source did not provide browser information.",
  cold_start: "No earlier account activity was available for comparison.",
  limited_account_history:
    "Fewer than five earlier successful logins were available.",
  truncated_retention_history:
    "The retention window limits the historical context available to this score.",
};
const featureNames: Record<string, string> = {
  current_failure: "Current login failed",
  account_failures_15m: "Account failures, prior 15 min",
  account_attempts_15m: "Account attempts, prior 15 min",
  source_attempts_5m: "Source attempts, prior 5 min",
  source_accounts_5m: "Distinct source accounts, prior 5 min",
  source_failure_ratio_5m: "Source failure ratio, prior 5 min",
  account_history_30d: "Account events, prior 30 days",
  account_successes_30d: "Account successes, prior 30 days",
  browser_novel: "Browser unfamiliar",
  hour_deviation: "Login hour deviation",
  seconds_since_previous: "Seconds since earlier account event",
  has_previous: "Earlier account event exists",
  account_missing: "Account unavailable",
  source_missing: "Source IP unavailable",
  browser_missing: "Browser unavailable",
};
const short = (value: string | null) =>
  value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "Account unavailable";
const stamp = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
const readable = (value: string) => value.replaceAll("_", " ");
const outcomeLabel = (value: string) =>
  value === "success" ? "Sign-in succeeded" : "Sign-in failed";
function decision(event: {
  flagged: boolean | null;
  job_state?: string | null;
}) {
  return event.flagged === true
    ? "Flagged"
    : event.flagged === false
      ? "No alert"
      : event.job_state === "failed"
        ? "Scoring failed"
        : "Awaiting score";
}
function Failure({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <div className="desk-message" role="alert">
      <CircleAlert size={24} aria-hidden="true" />
      <h2>Investigation needs attention.</h2>
      <p>{error.message}</p>
      {error instanceof AccessError && error.status === 401 ? (
        <Link to="/account">Open your account</Link>
      ) : (
        <button className="desk-button" onClick={retry}>
          Try again
        </button>
      )}
    </div>
  );
}
function ScoreTrack({
  title,
  score,
  threshold,
}: {
  title: string;
  score: number | null;
  threshold: number | null;
}) {
  if (score === null || threshold === null) return null;
  const maximum = Math.max(1, score, threshold) * 1.08;
  return (
    <div className="score-track">
      <div>
        <span>{title}</span>
        <strong>
          {score.toFixed(3)} <small>/ threshold {threshold.toFixed(3)}</small>
        </strong>
      </div>
      <div className="score-rail" aria-hidden="true">
        <span style={{ width: `${Math.min(100, (score / maximum) * 100)}%` }} />
        <i style={{ left: `${(threshold / maximum) * 100}%` }} />
      </div>
    </div>
  );
}

export default function InvestigationDashboard() {
  const { session } = useAuth();
  const token = session!.access_token;
  const identityKey = [session!.user.id, session!.expires_at];
  const cache = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState("");
  const evidence = useRef<HTMLElement>(null);
  const view = params.get("view") === "incidents" ? "incidents" : "events";
  const accountId = params.get("account") || "";
  const accountType =
    params.get("accountType") === "key" ? "account_key" : "user_id";
  const flaggedOnly = params.get("flagged") === "true";
  const outcome = params.get("outcome") || "";
  const filters = new URLSearchParams({ limit: "30" });
  if (flaggedOnly) filters.set("flagged", "true");
  if (outcome) filters.set("outcome", outcome);
  if (accountId) filters.set(accountType, accountId);
  const status = useQuery({
    queryKey: ["investigation", ...identityKey, "status"],
    meta: { private: true },
    retry: false,
    queryFn: ({ signal }) =>
      investigationRequest("/detection/status", token, statusSchema, signal),
  });
  const operations = useQuery({
    queryKey: ["investigation", ...identityKey, "operations"],
    meta: { private: true },
    retry: false,
    queryFn: ({ signal }) =>
      investigationRequest(
        "/telemetry/status",
        token,
        operationsSchema,
        signal,
      ),
  });
  const events = useInfiniteQuery({
    queryKey: ["investigation", ...identityKey, "events", filters.toString()],
    meta: { private: true },
    retry: false,
    enabled: view === "events",
    initialPageParam: "",
    queryFn: ({ signal, pageParam }) =>
      investigationRequest(
        `/investigation/events?${filters}${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
        token,
        pageSchema(eventSchema),
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
  const incidents = useInfiniteQuery({
    queryKey: ["investigation", ...identityKey, "incidents"],
    meta: { private: true },
    retry: false,
    enabled: view === "incidents",
    initialPageParam: "",
    queryFn: ({ signal, pageParam }) =>
      investigationRequest(
        `/incidents?limit=30${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
        token,
        pageSchema(incidentSchema),
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
  const allEvents = events.data?.pages.flatMap((p) => p.items) ?? [];
  const allIncidents = incidents.data?.pages.flatMap((p) => p.items) ?? [];
  const selectedIncident = params.get("incident") || allIncidents[0]?.id || "";
  const timeline = useInfiniteQuery({
    queryKey: ["investigation", ...identityKey, "timeline", selectedIncident],
    meta: { private: true },
    retry: false,
    enabled: view === "incidents" && Boolean(selectedIncident),
    initialPageParam: "",
    queryFn: ({ signal, pageParam }) =>
      investigationRequest(
        `/incidents/${encodeURIComponent(selectedIncident)}?limit=30${pageParam ? `&cursor=${encodeURIComponent(pageParam)}` : ""}`,
        token,
        pageSchema(timelineEventSchema),
        signal,
      ),
    getNextPageParam: (page) => page.next_cursor || undefined,
  });
  const timelineEvents = timeline.data?.pages.flatMap((p) => p.items) ?? [];
  const selectedEvent =
    params.get("event") ||
    (view === "events" ? allEvents[0]?.id : timelineEvents[0]?.id) ||
    "";
  const detail = useQuery({
    queryKey: ["investigation", ...identityKey, "event", selectedEvent],
    meta: { private: true },
    retry: false,
    enabled: Boolean(selectedEvent),
    queryFn: ({ signal }) =>
      investigationRequest(
        `/events/${encodeURIComponent(selectedEvent)}/detection`,
        token,
        detailSchema,
        signal,
      ),
  });
  useEffect(() => {
    if (window.matchMedia("(min-width: 951px)").matches)
      evidence.current?.scrollTo({ top: 0, behavior: "instant" });
  }, [selectedEvent, detail.data?.id]);
  const accessError = [
    status.error,
    operations.error,
    events.error,
    incidents.error,
    timeline.error,
    detail.error,
  ].find(
    (error) =>
      error instanceof AccessError && [401, 403].includes(error.status),
  );
  function change(values: Record<string, string | null>) {
    setParams((previous) => {
      const next = new URLSearchParams(previous);
      for (const [key, value] of Object.entries(values)) {
        if (value) next.set(key, value);
        else next.delete(key);
      }
      return next;
    });
  }
  function switchView(next: string) {
    setSearch("");
    change({
      view: next,
      event: null,
      incident: null,
      account: null,
      accountType: null,
      flagged: null,
      outcome: null,
    });
  }
  function chooseEvent(id: string) {
    change({ event: id });
    if (window.matchMedia("(max-width: 950px)").matches)
      evidence.current?.scrollIntoView({ behavior: "instant", block: "start" });
  }
  function accountHistory(event: EventDetail) {
    setSearch("");
    change({
      view: "events",
      account: event.user_id || event.account_key,
      accountType: event.user_id ? "id" : "key",
      incident: null,
      flagged: null,
      outcome: null,
      event: event.id,
    });
  }
  function refresh() {
    void cache.invalidateQueries({
      queryKey: ["investigation", ...identityKey],
    });
  }
  if (accessError) return <Failure error={accessError} retry={refresh} />;
  const data = status.data;
  const query = view === "events" ? events : incidents;
  const needle = search.toLowerCase().trim();
  const visibleEvents = allEvents.filter((e) =>
    [
      e.id,
      e.user_id,
      e.account_key,
      e.source_ip,
      e.user_agent,
      e.outcome,
      decision(e),
    ].some((v) => v?.toLowerCase().includes(needle)),
  );
  const visibleIncidents = allIncidents.filter((i) =>
    [i.id, i.entity_type, i.artifact_label].some((v) =>
      v.toLowerCase().includes(needle),
    ),
  );
  const busy = [status, operations, events, incidents, timeline, detail].some(
    (q) => q.isFetching,
  );
  const pending = data
    ? (data.queue.pending ?? 0) + (data.queue.processing ?? 0)
    : null;
  return (
    <div className="investigation-desk">
      <header className="desk-header">
        <div>
          <h1>Investigation desk.</h1>
          <p>Follow the sign-in. Examine the evidence.</p>
        </div>
        <div className="desk-refresh">
          <span>
            {status.dataUpdatedAt
              ? `Checked ${new Date(status.dataUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
              : "Not checked yet"}
          </span>
          <button className="desk-button" onClick={refresh} disabled={busy}>
            <RefreshCw
              size={16}
              className={busy ? "spin" : ""}
              aria-hidden="true"
            />
            {busy ? "Checking…" : "Refresh"}
          </button>
        </div>
      </header>
      <section className="desk-status" aria-label="Detection status">
        <div className="worker-status">
          <Activity size={20} aria-hidden="true" />
          <div>
            <strong>
              {!data
                ? "Worker status unavailable"
                : data.worker_ready
                  ? "Ready at last check"
                  : data.worker?.status === "model_unavailable"
                    ? "Model unavailable"
                    : "No ready worker"}
            </strong>
            <span>
              {data?.worker
                ? `Heartbeat ${stamp(data.worker.last_seen)}`
                : "No heartbeat recorded"}
            </span>
          </div>
          <span
            className={`worker-lamp ${data?.worker_ready ? "is-ready" : ""}`}
            aria-hidden="true"
          />
        </div>
        <dl>
          <div>
            <dt>Scored events</dt>
            <dd>{data?.scored.toLocaleString() ?? "—"}</dd>
          </div>
          <div>
            <dt>Flagged events</dt>
            <dd className="coral-number">
              {data?.flagged.toLocaleString() ?? "—"}
            </dd>
          </div>
          <div>
            <dt>Awaiting score</dt>
            <dd>{pending?.toLocaleString() ?? "—"}</dd>
          </div>
          <div>
            <dt>Failed jobs</dt>
            <dd>
              {data?.queue.failed?.toLocaleString() ?? (data ? "0" : "—")}
            </dd>
          </div>
        </dl>
      </section>
      {status.isError && (
        <Failure error={status.error} retry={() => void status.refetch()} />
      )}
      <OperationsHealth
        data={operations.data}
        error={operations.error}
        pending={operations.isPending}
        retry={() => void operations.refetch()}
      />
      <div className="desk-coverage">
        <ShieldCheck size={18} aria-hidden="true" />
        <p>
          <strong>Shadow mode.</strong> Flags support investigation and do not
          block sign-ins.{" "}
          {(operations.data?.failed_login_coverage ??
            data?.failed_login_coverage) === "provider_logs_recent_window"
            ? "Provider-confirmed password failures are collected from the recent hour. Attempted accounts are unavailable."
            : (operations.data?.failed_login_coverage ??
                  data?.failed_login_coverage) === "provider_logs_unhealthy"
              ? "Failed-login collection is overdue or incomplete. Current coverage could not be verified."
              : "Failed-login collection is not connected."}
        </p>
      </div>
      <div className="desk-toolbar">
        <nav aria-label="Investigation views">
          <button
            aria-pressed={view === "events"}
            onClick={() => switchView("events")}
          >
            <Fingerprint size={17} aria-hidden="true" />
            Event ledger
          </button>
          <button
            aria-pressed={view === "incidents"}
            onClick={() => switchView("incidents")}
          >
            <Layers3 size={17} aria-hidden="true" />
            Incidents
          </button>
        </nav>
        <label className="desk-search">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Search loaded records</span>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search loaded records"
            type="search"
          />
        </label>
      </div>
      {view === "events" && (
        <div className="desk-filters">
          <ListFilter size={16} aria-hidden="true" />
          <label>
            <span className="sr-only">Alert filter</span>
            <select
              value={flaggedOnly ? "flagged" : "all"}
              onChange={(e) =>
                change({
                  flagged: e.target.value === "flagged" ? "true" : null,
                  event: null,
                })
              }
            >
              <option value="all">All decisions</option>
              <option value="flagged">Flagged only</option>
            </select>
          </label>
          <label>
            <span className="sr-only">Login outcome</span>
            <select
              value={outcome}
              onChange={(e) => change({ outcome: e.target.value, event: null })}
            >
              <option value="">All outcomes</option>
              <option value="success">Succeeded</option>
              <option value="failure">Failed</option>
            </select>
          </label>
          {accountId && (
            <button
              className="account-filter"
              onClick={() =>
                change({ account: null, accountType: null, event: null })
              }
            >
              Account {short(accountId)}
              <X size={15} aria-hidden="true" />
              <span className="sr-only">Clear account filter</span>
            </button>
          )}
          <span>Retained records · newest first</span>
        </div>
      )}
      <div className="desk-grid">
        <section
          className="desk-ledger"
          aria-label={
            accountId
              ? "Account history"
              : view === "events"
                ? "Collected events"
                : "Grouped incidents"
          }
        >
          <div className="ledger-caption">
            <h2>
              {accountId
                ? "Account history"
                : view === "events"
                  ? "Collected events"
                  : "Grouped incidents"}
            </h2>
            <span>
              {view === "events" ? allEvents.length : allIncidents.length}{" "}
              loaded
            </span>
          </div>
          {query.isPending ? (
            <div className="desk-empty" role="status">
              <Clock3 size={28} aria-hidden="true" />
              <h3>Opening the ledger…</h3>
            </div>
          ) : query.isError ? (
            <Failure error={query.error} retry={() => void query.refetch()} />
          ) : view === "events" ? (
            <>
              {visibleEvents.length ? (
                <div className="event-rows">
                  {visibleEvents.map((e) => (
                    <EventRow
                      key={e.id}
                      event={e}
                      selected={selectedEvent === e.id}
                      choose={() => chooseEvent(e.id)}
                    />
                  ))}
                </div>
              ) : (
                <Empty
                  title={
                    allEvents.length && needle
                      ? "No loaded records match."
                      : "No events in this view."
                  }
                  text={
                    needle
                      ? "Search covers loaded rows. Clear it or load older records."
                      : "Collect authentication events, or change the decision and outcome filters."
                  }
                />
              )}
            </>
          ) : (
            <>
              {visibleIncidents.length ? (
                visibleIncidents.map((i) => (
                  <IncidentRow
                    key={i.id}
                    incident={i}
                    selected={selectedIncident === i.id}
                    choose={() => change({ incident: i.id, event: null })}
                  />
                ))
              ) : (
                <Empty
                  title={
                    needle
                      ? "No loaded incidents match."
                      : "No grouped alerts yet."
                  }
                  text={
                    needle
                      ? "Clear the search or load older incidents."
                      : "No retained events have produced an incident. This does not establish that all activity is safe."
                  }
                  action={() => switchView("events")}
                />
              )}
            </>
          )}
          {query.hasNextPage && (
            <button
              className="desk-load"
              onClick={() => void query.fetchNextPage()}
              disabled={query.isFetchingNextPage}
            >
              <ArrowDown size={16} aria-hidden="true" />
              {query.isFetchingNextPage ? "Loading…" : "Load older records"}
            </button>
          )}
          <footer className="ledger-foot">
            <span>Source timestamps</span>
            <span>{Intl.DateTimeFormat().resolvedOptions().timeZone}</span>
          </footer>
        </section>
        <section
          ref={evidence}
          id="evidence-pane"
          className="desk-evidence"
          aria-label="Selected event evidence"
          tabIndex={-1}
        >
          {view === "incidents" && selectedIncident && (
            <section className="incident-timeline">
              <div className="evidence-section-heading">
                <Layers3 size={18} aria-hidden="true" />
                <h2>Incident timeline</h2>
              </div>
              <p className="desk-hint">
                {short(selectedIncident)} · fixed 15-minute grouping · newest
                first
              </p>
              {timeline.isPending ? (
                <p role="status">Loading related events…</p>
              ) : timeline.isError ? (
                <Failure
                  error={timeline.error}
                  retry={() => void timeline.refetch()}
                />
              ) : timelineEvents.length ? (
                <ol>
                  {timelineEvents.map((e) => (
                    <li key={e.id}>
                      <button
                        onClick={() => chooseEvent(e.id)}
                        aria-pressed={selectedEvent === e.id}
                      >
                        <span className="timeline-dot" aria-hidden="true" />
                        <time dateTime={e.occurred_at}>
                          {stamp(e.occurred_at)}
                        </time>
                        <strong>{outcomeLabel(e.outcome)}</strong>
                        <ChevronRight size={15} aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ol>
              ) : (
                <p>No retained events remain in this incident.</p>
              )}
              {timeline.hasNextPage && (
                <button
                  className="desk-load"
                  disabled={timeline.isFetchingNextPage}
                  onClick={() => void timeline.fetchNextPage()}
                >
                  Load older incident events
                </button>
              )}
            </section>
          )}
          {!selectedEvent ? (
            <Empty
              title="The evidence starts here."
              text="Select an event to inspect its context, signals, and model decision."
            />
          ) : detail.isPending ? (
            <div className="desk-empty" role="status">
              Reading event evidence…
            </div>
          ) : detail.isError ? (
            <Failure error={detail.error} retry={() => void detail.refetch()} />
          ) : detail.data ? (
            <EventEvidence
              key={detail.data.id}
              event={detail.data}
              history={() => accountHistory(detail.data!)}
            />
          ) : null}
        </section>
      </div>
      <p className="desk-disclaimer">
        Experimental model trained on synthetic data. Anomaly scores are not
        probabilities of compromise. Refresh to check new records and worker
        readiness.
      </p>
    </div>
  );
}
function Empty({
  title,
  text,
  action,
}: {
  title: string;
  text: string;
  action?: () => void;
}) {
  return (
    <div className="desk-empty">
      <FolderSearch size={34} strokeWidth={1.3} aria-hidden="true" />
      <h3>{title}</h3>
      <p>{text}</p>
      {action && (
        <button className="desk-button" onClick={action}>
          Open event ledger
          <ArrowRight size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
function EventRow({
  event: e,
  selected,
  choose,
}: {
  event: InvestigationEvent;
  selected: boolean;
  choose: () => void;
}) {
  return (
    <button
      className={`event-row ${selected ? "is-selected" : ""}`}
      aria-pressed={selected}
      aria-controls="evidence-pane"
      onClick={choose}
    >
      <span
        className={`event-mark ${e.flagged ? "mark-flagged" : ""}`}
        aria-hidden="true"
      >
        {e.flagged ? <CircleAlert size={18} /> : <Fingerprint size={18} />}
      </span>
      <span className="event-copy">
        <strong>{outcomeLabel(e.outcome)}</strong>
        <span>
          {e.source_ip || "IP unavailable"} <i>·</i>{" "}
          {short(e.user_id || e.account_key)}
        </span>
        <time dateTime={e.occurred_at}>{stamp(e.occurred_at)}</time>
      </span>
      <span className="event-decision">
        <span className={`decision-pill ${e.flagged ? "is-flagged" : ""}`}>
          {decision(e)}
        </span>
        <ChevronRight size={16} aria-hidden="true" />
      </span>
    </button>
  );
}
function IncidentRow({
  incident: i,
  selected,
  choose,
}: {
  incident: Incident;
  selected: boolean;
  choose: () => void;
}) {
  return (
    <button
      className={`event-row incident-row ${selected ? "is-selected" : ""}`}
      aria-pressed={selected}
      onClick={choose}
    >
      <span className="event-mark mark-flagged" aria-hidden="true">
        <Layers3 size={18} />
      </span>
      <span className="event-copy">
        <strong>
          {i.entity_type === "source"
            ? "Source activity cluster"
            : i.entity_type === "account"
              ? "Account activity cluster"
              : "Flagged event"}
        </strong>
        <span>
          {i.event_count} retained {i.event_count === 1 ? "event" : "events"} ·{" "}
          {short(i.id)}
        </span>
        <time dateTime={i.last_seen}>Last seen {stamp(i.last_seen)}</time>
      </span>
      <ChevronRight size={16} aria-hidden="true" />
    </button>
  );
}
function EventEvidence({
  event: e,
  history,
}: {
  event: EventDetail;
  history: () => void;
}) {
  const scored = e.job_state === "processed" && e.flagged !== null;
  return (
    <div className="evidence-content">
      <header className="evidence-header">
        <div>
          <span className={`decision-pill ${e.flagged ? "is-flagged" : ""}`}>
            {decision(e)}
          </span>
          <h2>{outcomeLabel(e.outcome)}</h2>
          <time dateTime={e.occurred_at}>{stamp(e.occurred_at)}</time>
        </div>
        <span
          className={`evidence-seal ${e.flagged ? "is-flagged" : ""}`}
          aria-hidden="true"
        >
          {e.flagged ? (
            <CircleAlert size={29} strokeWidth={1.4} />
          ) : scored ? (
            <Check size={29} strokeWidth={1.4} />
          ) : (
            <Clock3 size={29} strokeWidth={1.4} />
          )}
        </span>
      </header>
      <dl className="evidence-facts">
        <div>
          <dt>Account</dt>
          <dd>{short(e.user_id || e.account_key)}</dd>
        </div>
        <div>
          <dt>Source IP</dt>
          <dd>{e.source_ip || "Not provided"}</dd>
        </div>
        <div>
          <dt>Event source</dt>
          <dd>
            {e.source === "supabase_audit"
              ? "Supabase audit"
              : "Trusted server adapter"}
          </dd>
        </div>
        <div>
          <dt>Browser context</dt>
          <dd>{e.user_agent || "Not provided"}</dd>
        </div>
      </dl>
      {(e.user_id || e.account_key) && (
        <button className="account-history-link" onClick={history}>
          <Fingerprint size={16} aria-hidden="true" />
          View account history
          <ArrowRight size={15} aria-hidden="true" />
        </button>
      )}
      <section className="evidence-section">
        <div className="evidence-section-heading">
          <SlidersHorizontal size={18} aria-hidden="true" />
          <h3>Detector decision</h3>
        </div>
        {scored ? (
          <>
            <ScoreTrack
              title="Isolation Forest"
              score={e.ml_score}
              threshold={e.ml_threshold}
            />
            <ScoreTrack
              title="Security rules"
              score={e.rule_score}
              threshold={e.rule_threshold}
            />
            <p className="desk-hint">
              A flag is raised when either calibrated threshold is exceeded.
              Scores are not percentages.
            </p>
          </>
        ) : (
          <p>
            {e.job_state === "failed"
              ? `Scoring stopped after ${e.attempts ?? 0} attempts. An operator must review ${readable(e.last_error || "the worker error")}.`
              : "This event has not been scored yet. Check the worker status and refresh."}
          </p>
        )}
      </section>
      <section className="evidence-section">
        <h3>Observed signals</h3>
        {e.signals?.length ? (
          <ul className="signal-list">
            {e.signals.map((s) => (
              <li key={s}>
                <CircleAlert size={17} aria-hidden="true" />
                <div>
                  <strong>{signals[s]?.[0] || readable(s)}</strong>
                  <p>
                    {signals[s]?.[1] || "Recorded by this detector version."}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="desk-hint">
            {scored
              ? "Neither detector crossed its alert threshold. This is not a guarantee of a safe login."
              : "Signals will appear after scoring."}
          </p>
        )}
      </section>
      {Boolean(e.context_warnings?.length) && (
        <section className="context-warnings">
          <h3>
            <CircleAlert size={17} aria-hidden="true" />
            Context limits
          </h3>
          <ul>
            {e.context_warnings!.map((w) => (
              <li key={w}>{warnings[w] || readable(w)}</li>
            ))}
          </ul>
        </section>
      )}
      <details className="evidence-details">
        <summary>Model and processing record</summary>
        <dl>
          <dt>Model</dt>
          <dd>{e.artifact_label || "Not assigned"}</dd>
          <dt>Model fingerprint</dt>
          <dd className="mono">{e.model_version_id || "Not assigned"}</dd>
          <dt>Feature version</dt>
          <dd>{e.feature_version || "Not assigned"}</dd>
          <dt>History snapshot</dt>
          <dd>{e.history_as_of ? stamp(e.history_as_of) : "Not available"}</dd>
          <dt>Scored at</dt>
          <dd>{e.scored_at ? stamp(e.scored_at) : "Not scored"}</dd>
          <dt>Received at</dt>
          <dd>{stamp(e.received_at)}</dd>
          <dt>Event ID</dt>
          <dd className="mono">{e.id}</dd>
          <dt>Account identifier</dt>
          <dd className="mono">
            {e.user_id || e.account_key || "Unavailable"}
          </dd>
        </dl>
      </details>
      {e.features && (
        <details className="evidence-details">
          <summary>Feature snapshot ({Object.keys(e.features).length})</summary>
          <p className="desk-hint">
            Observed inputs at scoring time; these values do not explain the
            model's individual feature contributions.
          </p>
          <dl>
            {Object.entries(e.features).map(([key, value]) => (
              <div key={key}>
                <dt>{featureNames[key] || readable(key)}</dt>
                <dd>{Number.isInteger(value) ? value : value.toFixed(3)}</dd>
              </div>
            ))}
          </dl>
        </details>
      )}
    </div>
  );
}
