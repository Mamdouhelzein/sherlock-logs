import { Database, Clock3 } from "lucide-react";
import type { OperationsStatus } from "./api";

const date = (at: string | null) =>
  at ? new Date(at).toLocaleString() : "Not recorded";
export function OperationsHealth({
  data,
  error,
  pending,
  retry,
}: {
  data?: OperationsStatus;
  error: Error | null;
  pending: boolean;
  retry: () => void;
}) {
  if (pending)
    return (
      <p className="operations-notice" role="status">
        Checking collection and cleanup…
      </p>
    );
  if (error || !data)
    return (
      <div className="operations-notice">
        <span>
          Collection monitoring unavailable. Scoring status is shown separately.
        </span>
        <button onClick={retry}>Retry collection check</button>
      </div>
    );
  const c = data.collection,
    r = data.retention;
  const collectionLabel =
    c.status === "running"
      ? c.lease_fresh
        ? "Collecting now"
        : "Collector lease expired"
      : c.status === "error"
        ? "Collection failed"
        : c.status === "partial"
          ? "Collection incomplete"
          : c.status === "stopped"
            ? "Collector stopped"
            : c.status === "idle"
              ? "Collection not started"
              : c.healthy
                ? "Automatic collection healthy"
                : c.full_scan_overdue
                  ? "Full rescan overdue"
                  : "Collector overdue";
  const retentionLabel = !r.enabled
    ? "Cleanup not enabled"
    : r.healthy
      ? "Cleanup healthy"
      : r.status === "error"
        ? "Cleanup failed"
        : r.backlog
          ? "Cleanup backlog"
          : r.last_success_at
            ? "Cleanup overdue"
            : "Cleanup not verified";
  return (
    <section
      className="operations-health"
      aria-label="Collection and retention"
    >
      <div className={c.healthy ? "operation-ready" : "operation-attention"}>
        <Database size={18} aria-hidden="true" />
        <div>
          <strong>{collectionLabel}</strong>
          <p>
            Every {c.interval_seconds} seconds while the collector is running.
          </p>
          <small>Last successful scan: {date(c.last_success_at)}</small>
        </div>
      </div>
      <div className={r.healthy ? "operation-ready" : "operation-attention"}>
        <Clock3 size={18} aria-hidden="true" />
        <div>
          <strong>{retentionLabel}</strong>
          <p>
            Hourly cleanup keeps {r.keep_days} days of stored event history.
          </p>
          <small>Last successful cleanup: {date(r.last_success_at)}</small>
        </div>
      </div>
      <details>
        <summary>Collection and cleanup details</summary>
        <dl>
          <div>
            <dt>Last scan window</dt>
            <dd>{c.scan_full ? "Full retained history" : "Recent hour"}</dd>
          </div>
          <div>
            <dt>Last run counts</dt>
            <dd>
              {["error", "stopped"].includes(c.status)
                ? "Not reported for failed or stopped runs."
                : `${c.counts.scanned} scanned, ${c.counts.inserted} added, ${c.counts.duplicates} duplicates, ${c.counts.rejected} rejected`}
            </dd>
          </div>
          <div>
            <dt>Last full rescan</dt>
            <dd>{date(c.last_full_scan_at)}</dd>
          </div>
          <div>
            <dt>Next collection attempt</dt>
            <dd>
              {c.status === "stopped"
                ? "Not scheduled while stopped"
                : date(c.next_run_at)}
            </dd>
          </div>
          <div>
            <dt>Expired events deleted in last cleanup</dt>
            <dd>{r.deleted}</dd>
          </div>
          <div>
            <dt>Failed-login source</dt>
            <dd>
              {data.failed_login_coverage === "provider_logs_recent_window"
                ? "Provider Auth logs · recent hour"
                : data.failed_login_coverage === "provider_logs_unhealthy"
                  ? "Provider Auth logs · overdue or incomplete"
                  : "Not connected"}
            </dd>
          </div>
          {data.failure_source?.last_success_at && (
            <>
              <div>
                <dt>Last successful failure scan</dt>
                <dd>{date(data.failure_source.last_success_at)}</dd>
              </div>
              <div>
                <dt>Failure records scanned</dt>
                <dd>{data.failure_source.scanned ?? "Not recorded"}</dd>
              </div>
            </>
          )}
        </dl>
        <p>
          Successful-login full rescans are due every six hours to find late
          records. Provider failure scans cover the recent hour; longer outages
          can leave gaps. Invalid credentials do not identify the attempted
          account. This panel reflects the last check.
        </p>
      </details>
    </section>
  );
}
