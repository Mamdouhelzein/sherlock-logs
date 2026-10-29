import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import {
  ArrowRight,
  ArrowUpRight,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleCheck,
  CodeXml,
  Database,
  Fingerprint,
  GitBranch,
  LayoutDashboard,
  RefreshCw,
  ScanEye,
  Server,
  ShieldCheck,
  Terminal,
  WifiOff,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { fetchSystem, getApiOrigin } from "./lib/api";

const repository = "https://github.com/Mamdouhelzein/sherlock-logs";
const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/architecture", label: "System architecture", icon: GitBranch },
  { to: "/setup", label: "Local setup", icon: Terminal },
];

const roadmap = [
  {
    title: "Repository foundation",
    description: "Architecture, scope, and project structure.",
    state: "Complete",
  },
  {
    title: "Application foundation",
    description: "React workspace connected to FastAPI.",
    state: "Current",
  },
  {
    title: "Identity & access",
    description: "Supabase authentication and access policies.",
    state: "Up next",
  },
  {
    title: "Behavioral detection",
    description: "Trusted events, features, and ML evaluation.",
    state: "Planned",
  },
];

function Status({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "green" | "amber" | "neutral";
}) {
  return (
    <span className={`status status-${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}

function SectionHeading({ number, title }: { number: string; title: string }) {
  return (
    <div className="section-heading">
      <span className="mono">{number}</span>
      <h2>{title}</h2>
    </div>
  );
}

export default function App() {
  const location = useLocation();
  const currentPage =
    navigation.find((item) => item.to === location.pathname)?.label ??
    "Page not found";
  const query = useQuery({
    queryKey: ["system"],
    queryFn: ({ signal }) => fetchSystem(signal),
  });
  const current = query.isError ? undefined : query.data;
  const connectionLabel = query.isPending
    ? "Checking API"
    : query.isError
      ? "API unavailable"
      : "API reachable";
  let docsUrl: string | null = null;
  try {
    docsUrl = `${getApiOrigin()}/docs`;
  } catch {
    /* Configuration errors appear in the status panel. */
  }

  return (
    <div className="workspace">
      <a href="#main-content" className="skip-link">
        Skip to content
      </a>
      <aside className="sidebar" aria-label="Workspace navigation">
        <Link className="brand" to="/" aria-label="Sherlock Logs overview">
          <span className="brand-mark">
            <ScanEye size={24} aria-hidden="true" />
          </span>
          <span>
            Sherlock<span className="brand-light"> Logs</span>
            <small>THE INVESTIGATION WORKSPACE</small>
          </span>
        </Link>
        <div className="workspace-selector">
          <span className="workspace-avatar">SL</span>
          <div>
            Local workspace<small>Development environment</small>
          </div>
          <span className="mono workspace-version">v0.1</span>
        </div>
        <span className="nav-caption">WORKSPACE</span>
        <nav className="main-nav">
          {navigation.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} end={to === "/"}>
              <Icon size={18} aria-hidden="true" />
              <span>{label}</span>
              <ChevronRight
                size={15}
                className="nav-chevron"
                aria-hidden="true"
              />
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={20} aria-hidden="true" />
          <p>
            A clearer view of
            <br />
            <strong>unusual behavior.</strong>
          </p>
          <span>Built to investigate, one signal at a time.</span>
        </div>
        <div className="sidebar-bottom">
          <a href={repository} target="_blank" rel="noreferrer">
            <CodeXml size={18} aria-hidden="true" />
            Project repository
            <ArrowUpRight size={15} aria-hidden="true" />
          </a>
          <span className="mono">FOUNDATION RELEASE · 0.1.0</span>
        </div>
      </aside>

      <div className="workspace-body">
        <header className="topbar">
          <div>
            <span className="breadcrumb-muted">Workspace</span>
            <ChevronRight size={14} aria-hidden="true" />
            <span>{currentPage}</span>
          </div>
          <span className="environment">
            <span />
            Local development
          </span>
        </header>
        <main id="main-content" tabIndex={-1}>
          <Routes>
            <Route
              path="/"
              element={
                <>
                  <div className="page-label">
                    <span className="mono">CASE FILE 001</span>
                    <span className="label-divider" />
                    APPLICATION FOUNDATION
                  </div>
                  <div className="hero">
                    <div>
                      <h1>
                        Every investigation
                        <br />
                        starts with a <em>signal.</em>
                      </h1>
                      <p>
                        Your security workspace is taking shape. Establish the
                        connection,
                        <br className="desktop-break" /> then build the
                        intelligence behind it.
                      </p>
                    </div>
                    <div className="hero-seal" aria-hidden="true">
                      <div className="seal-orbit" />
                      <ScanEye size={66} strokeWidth={1} />
                      <span className="mono">OBSERVE. UNDERSTAND.</span>
                    </div>
                  </div>

                  <div className="foundation-banner">
                    <span className="banner-icon">
                      <Check size={18} aria-hidden="true" />
                    </span>
                    <div>
                      <strong>The foundation is in place.</strong>
                      <span>
                        React interface. FastAPI service. One connected
                        workspace.
                      </span>
                    </div>
                    <Status tone="green">Step 02</Status>
                  </div>

                  <div className="overview-grid">
                    <section className="connection-section">
                      <SectionHeading number="01" title="Connection overview" />
                      <div className="panel connection-panel">
                        <div className="panel-top">
                          <span className="icon-tile">
                            <Server size={21} aria-hidden="true" />
                          </span>
                          <Status
                            tone={
                              current
                                ? "green"
                                : query.isError
                                  ? "amber"
                                  : "neutral"
                            }
                          >
                            {connectionLabel}
                          </Status>
                        </div>
                        <div aria-live="polite" aria-atomic="true">
                          <h3>
                            {query.isPending
                              ? "Looking for a signal…"
                              : query.isError
                                ? "Connection needs attention."
                                : "A connection, confirmed."}
                          </h3>
                          <p className="connection-description">
                            {query.isPending
                              ? "Contacting the backend for its current system status."
                              : query.isError
                                ? query.error.message
                                : "The workspace can reach your FastAPI service. This confirms the application connection, not readiness of future integrations."}
                          </p>
                        </div>
                        <div className="connection-details">
                          <div>
                            <span>Service</span>
                            <strong className="mono">sherlock-logs-api</strong>
                          </div>
                          <div>
                            <span>Response time</span>
                            <strong className="mono">
                              {current ? `${current.latencyMs} ms` : "—"}
                            </strong>
                          </div>
                          <div>
                            <span>Release</span>
                            <strong className="mono">
                              {current ? `v${current.snapshot.version}` : "—"}
                            </strong>
                          </div>
                          <div>
                            <span>Last checked</span>
                            <strong className="mono">
                              {current
                                ? new Date(
                                    current.snapshot.checked_at,
                                  ).toLocaleTimeString([], {
                                    hour: "2-digit",
                                    minute: "2-digit",
                                    second: "2-digit",
                                  })
                                : "—"}
                            </strong>
                          </div>
                        </div>
                        <div className="connection-actions">
                          <Button
                            variant="outline"
                            onClick={() => void query.refetch()}
                            disabled={query.isFetching}
                          >
                            <RefreshCw
                              size={15}
                              className={query.isFetching ? "spin" : ""}
                              aria-hidden="true"
                            />
                            {query.isFetching ? "Checking…" : "Check again"}
                          </Button>
                          {docsUrl && (
                            <Button variant="ghost" asChild>
                              <a
                                href={docsUrl}
                                target="_blank"
                                rel="noreferrer"
                              >
                                API docs
                                <ArrowUpRight size={15} aria-hidden="true" />
                              </a>
                            </Button>
                          )}
                        </div>
                        {query.isError && (
                          <Link to="/setup" className="recovery-link">
                            <WifiOff size={14} aria-hidden="true" />
                            Open the startup guide
                            <ArrowRight size={14} aria-hidden="true" />
                          </Link>
                        )}
                      </div>
                      <p className="section-footnote">
                        A manual check of the service. No login telemetry is
                        collected yet.
                      </p>
                    </section>
                    <section className="roadmap-section">
                      <SectionHeading number="02" title="The path ahead" />
                      <div className="panel roadmap-panel">
                        {roadmap.map((item, index) => (
                          <div
                            key={item.title}
                            className={`roadmap-item roadmap-${item.state.toLowerCase().replace(" ", "-")}`}
                          >
                            <span className="roadmap-index mono">
                              {item.state === "Complete" ? (
                                <Check size={15} aria-hidden="true" />
                              ) : (
                                `0${index + 1}`
                              )}
                            </span>
                            <div>
                              <div className="roadmap-title">
                                <h3>{item.title}</h3>
                                <span>{item.state}</span>
                              </div>
                              <p>{item.description}</p>
                            </div>
                          </div>
                        ))}
                        <a
                          className="roadmap-link"
                          href={`${repository}/blob/main/ROADMAP.md`}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Explore the full roadmap
                          <ArrowUpRight size={16} aria-hidden="true" />
                        </a>
                      </div>
                    </section>
                  </div>

                  <section className="integrations-section">
                    <SectionHeading
                      number="03"
                      title="Intelligence takes a foundation"
                    />
                    <div className="integration-grid">
                      {[
                        {
                          id: "authentication",
                          name: "Identity & access",
                          icon: Fingerprint,
                          tag: "Not configured",
                          description:
                            "Supabase authentication will establish who can access the workspace.",
                        },
                        {
                          id: "database",
                          name: "Event storage",
                          icon: Database,
                          tag: "Not configured",
                          description:
                            "PostgreSQL will preserve trusted login events and investigation records.",
                        },
                        {
                          id: "detector",
                          name: "Behavioral intelligence",
                          icon: BrainCircuit,
                          tag: "Not trained",
                          description:
                            "Isolation Forest will learn unusual patterns from historical login behavior.",
                        },
                      ].map(({ id, name, icon: Icon, tag, description }) => (
                        <article className="panel integration-card" key={id}>
                          <div className="integration-top">
                            <Icon
                              size={23}
                              strokeWidth={1.5}
                              aria-hidden="true"
                            />
                            <span className="mono">UPCOMING</span>
                          </div>
                          <h3>{name}</h3>
                          <p>
                            {current?.snapshot.integrations.find(
                              (item) => item.id === id,
                            )?.detail ?? description}
                          </p>
                          <Status>{tag}</Status>
                        </article>
                      ))}
                    </div>
                  </section>
                </>
              }
            />
            <Route path="/architecture" element={<Architecture />} />
            <Route path="/setup" element={<Setup docsUrl={docsUrl} />} />
            <Route
              path="*"
              element={
                <div className="document-page">
                  <span className="page-label">404 · UNKNOWN PATH</span>
                  <h1>This case file is missing.</h1>
                  <p>The page does not exist in this workspace.</p>
                  <Button asChild>
                    <Link to="/">
                      Return to overview
                      <ArrowRight size={16} aria-hidden="true" />
                    </Link>
                  </Button>
                </div>
              }
            />
          </Routes>
          <footer className="footer">
            <span>
              <ScanEye size={16} aria-hidden="true" />
              Sherlock Logs <span className="footer-divider">/</span> The case
              of the suspicious sign-in.
            </span>
            <span>Built with curiosity. Backed by evidence.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

function Architecture() {
  return (
    <div className="document-page">
      <div className="page-label mono">SYSTEM BLUEPRINT</div>
      <h1>Follow the signal.</h1>
      <p className="document-lead">
        The website handles identity. Sherlock Logs will turn trusted activity
        into evidence for investigation.
      </p>
      <div className="architecture-flow">
        {[
          {
            icon: LayoutDashboard,
            title: "React workspace",
            text: "Browser interface, navigation, and a real connection check.",
            state: "Available now",
          },
          {
            icon: Server,
            title: "FastAPI service",
            text: "Validated system status and process-liveness endpoints.",
            state: "Available now",
          },
          {
            icon: Database,
            title: "Trusted event pipeline",
            text: "Server-side authentication events, historical features, and durable processing.",
            state: "Planned",
          },
          {
            icon: BrainCircuit,
            title: "Detection & investigation",
            text: "Security rules, Isolation Forest scores, and grouped incidents.",
            state: "Planned",
          },
        ].map(({ icon: Icon, title, text, state }, index) => (
          <article className="panel architecture-step" key={title}>
            <span className="mono architecture-number">0{index + 1}</span>
            <Icon size={25} aria-hidden="true" />
            <div>
              <h2>{title}</h2>
              <p>{text}</p>
            </div>
            <Status tone={state === "Available now" ? "green" : "neutral"}>
              {state}
            </Status>
          </article>
        ))}
      </div>
      <div className="boundary-note">
        <ShieldCheck size={22} aria-hidden="true" />
        <div>
          <h2>A deliberate boundary</h2>
          <p>
            ML scoring will support investigation. Authentication protections
            will operate independently, and the browser will never be trusted to
            declare its own login outcomes. This release has no authentication,
            event ingestion, or trained model.
          </p>
        </div>
      </div>
      <Button variant="outline" asChild>
        <a
          href={`${repository}/blob/main/ARCHITECTURE.md`}
          target="_blank"
          rel="noreferrer"
        >
          Read the full architecture
          <ArrowUpRight size={16} aria-hidden="true" />
        </a>
      </Button>
    </div>
  );
}

function Setup({ docsUrl }: { docsUrl: string | null }) {
  return (
    <div className="document-page">
      <div className="page-label mono">DEVELOPER FIELD NOTES</div>
      <h1>Start the investigation.</h1>
      <p className="document-lead">
        Use Node.js 22.12+ and Python 3.12+. No Supabase account, database, or
        paid API is required for this milestone.
      </p>
      <div className="setup-grid">
        <section className="panel setup-card">
          <span className="step-number mono">
            TERMINAL 01 · FROM REPOSITORY ROOT
          </span>
          <h2>Start the backend</h2>
          <pre>
            <code>
              {
                "python3 -m venv backend/.venv\nbackend/.venv/bin/python -m pip install \\\n  -r backend/requirements-dev.lock\nbackend/.venv/bin/python -m pip install \\\n  --no-deps -e backend\nbackend/.venv/bin/uvicorn \\\n  sherlock_api.main:app --reload \\\n  --host 127.0.0.1 --port 8000"
              }
            </code>
          </pre>
          <p>
            On Windows, use <code>backend\\.venv\\Scripts\\python.exe</code> and
            the equivalent uvicorn executable. Full platform instructions are in
            the README.
          </p>
        </section>
        <section className="panel setup-card">
          <span className="step-number mono">
            TERMINAL 02 · FROM REPOSITORY ROOT
          </span>
          <h2>Start the frontend</h2>
          <pre>
            <code>{"cd frontend\nnpm ci\nnpm run dev"}</code>
          </pre>
          <p>
            Open <code>http://127.0.0.1:5173</code>. The API defaults to{" "}
            <code>http://127.0.0.1:8000</code>. Optional overrides are
            documented in the root <code>.env.example</code>.
          </p>
        </section>
      </div>
      <div className="boundary-note">
        <CircleCheck size={22} aria-hidden="true" />
        <div>
          <h2>What a successful check means</h2>
          <p>
            The overview should show “API reachable.” That verifies a
            browser-to-backend request. It does not claim that authentication,
            storage, or the ML detector is ready.
          </p>
        </div>
      </div>
      <div className="document-actions">
        <Button asChild>
          <Link to="/">
            Check the connection
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        </Button>
        {docsUrl && (
          <Button variant="outline" asChild>
            <a href={docsUrl} target="_blank" rel="noreferrer">
              Open API documentation
              <ArrowUpRight size={16} aria-hidden="true" />
            </a>
          </Button>
        )}
      </div>
    </div>
  );
}
