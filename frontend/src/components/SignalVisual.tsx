import { BrainCircuit, Fingerprint, ScanEye, Server } from "lucide-react";

export function SignalVisual() {
  return (
    <figure className="signal-visual">
      <div className="signal-stage" aria-hidden="true">
        <span className="signal-axis axis-horizontal" />
        <span className="signal-axis axis-vertical" />
        <div className="radar-ring ring-outer" />
        <div className="radar-ring ring-middle" />
        <div className="radar-ring ring-inner" />
        <div className="radar-sweep" />
        <div className="signal-core">
          <ScanEye size={44} strokeWidth={1.1} />
          <span>SHERLOCK</span>
        </div>
        <div className="signal-node node-identity">
          <Fingerprint size={18} />
          <span>IDENTITY</span>
        </div>
        <div className="signal-node node-api">
          <Server size={18} />
          <span>EVENTS</span>
        </div>
        <div className="signal-node node-model">
          <BrainCircuit size={18} />
          <span>INTELLIGENCE</span>
        </div>
        <span className="signal-coordinate coordinate-top mono">OBSERVE</span>
        <span className="signal-coordinate coordinate-bottom mono">
          UNDERSTAND
        </span>
      </div>
      <figcaption>
        <span />
        Architecture illustration · detection is planned
      </figcaption>
    </figure>
  );
}
