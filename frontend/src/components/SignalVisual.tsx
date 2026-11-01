import { Database, Fingerprint, LockKeyhole, ScanEye } from "lucide-react";
import { useRef, type PointerEvent } from "react";

export function SignalVisual() {
  const bounds = useRef<DOMRect | null>(null);
  function followPointer(event: PointerEvent<HTMLElement>) {
    if (event.pointerType !== "mouse" || !bounds.current) return;
    const box = bounds.current;
    const x = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    const y = Math.max(0, Math.min(1, (event.clientY - box.top) / box.height));
    event.currentTarget.style.setProperty("--tilt-x", `${(0.5 - y) * 5}deg`);
    event.currentTarget.style.setProperty("--tilt-y", `${(x - 0.5) * 5}deg`);
    event.currentTarget.style.setProperty("--pointer-x", `${x * 100}%`);
    event.currentTarget.style.setProperty("--pointer-y", `${y * 100}%`);
  }
  function releasePointer(event: PointerEvent<HTMLElement>) {
    bounds.current = null;
    event.currentTarget.style.removeProperty("--tilt-x");
    event.currentTarget.style.removeProperty("--tilt-y");
  }
  return (
    <figure
      className="signal-visual"
      aria-label="Authentication event collection workflow"
      onPointerEnter={(event) => {
        bounds.current = event.currentTarget.getBoundingClientRect();
      }}
      onPointerMove={followPointer}
      onPointerLeave={releasePointer}
    >
      <svg
        className="trail-topology"
        viewBox="0 0 500 500"
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <path
          className="topology-wire"
          d="M-20 100H42L88 146V210M520 120H466L425 162V230M-20 390H70L116 344M520 410H432L395 370"
        />
        <path
          className="topology-flow"
          d="M-20 100H42L88 146V210M520 120H466L425 162V230"
        />
        <circle cx="42" cy="100" r="4" />
        <circle cx="466" cy="120" r="4" />
        <circle cx="70" cy="390" r="4" />
        <circle cx="432" cy="410" r="4" />
      </svg>
      <div className="trail-heading">
        <span>The evidence trail</span>
        <ScanEye size={24} strokeWidth={1.4} aria-hidden="true" />
      </div>
      <div className="trail-record">
        <span className="trail-scan" aria-hidden="true" />
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
      <figcaption>
        Animated workflow illustration. No live activity shown.
      </figcaption>
    </figure>
  );
}
