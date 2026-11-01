import { Database, Fingerprint, LockKeyhole, ScanEye } from "lucide-react";

export function SignalVisual() {
  return (
    <figure
      className="signal-visual"
      aria-label="Authentication event collection workflow"
    >
      <div className="trail-heading">
        <span>The evidence trail</span>
        <ScanEye size={24} strokeWidth={1.4} aria-hidden="true" />
      </div>
      <div className="trail-record">
        <div className="record-heading">
          <Fingerprint size={22} strokeWidth={1.4} aria-hidden="true" />
          <strong>Authentication event</strong>
          <span>Source</span>
        </div>
        <dl>
          <div>
            <dt>Outcome</dt>
            <dd>Provider-verified</dd>
          </div>
          <div>
            <dt>Time</dt>
            <dd>Source timestamp</dd>
          </div>
          <div>
            <dt>Context</dt>
            <dd>When available</dd>
          </div>
        </dl>
      </div>
      <div className="trail-connector" aria-hidden="true">
        <span />
      </div>
      <div className="trail-store">
        <Database size={22} strokeWidth={1.5} aria-hidden="true" />
        <div>
          <strong>Private event record</strong>
          <span>Stored with restricted access</span>
        </div>
        <LockKeyhole size={17} aria-hidden="true" />
      </div>
      <div className="trail-next">
        <span className="trail-next-dot" aria-hidden="true" />
        <div>
          <strong>Behavioral review</strong>
          <span>Model training is the next stage.</span>
        </div>
      </div>
      <figcaption>Collection workflow, not a live event.</figcaption>
    </figure>
  );
}
