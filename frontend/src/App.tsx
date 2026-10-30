import { useEffect, useState } from "react";
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
  Sparkles,
  Terminal,
  WifiOff,
} from "lucide-react";
import { Button } from "./components/ui/button";
import { CommandMenu } from "./components/CommandMenu";
import { SignalVisual } from "./components/SignalVisual";
import { AuthCallback, AuthPage, ProtectedPage } from "./auth/AuthPages";
import { fetchSystem, getApiOrigin } from "./lib/api";

const repository = "https://github.com/Mamdouhelzein/sherlock-logs";
const navigation = [
  { to: "/", label: "Overview", icon: LayoutDashboard },
  { to: "/account", label: "Your account", icon: Fingerprint },
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
    state: "Complete",
  },
  {
    title: "Identity & access",
    description: "Supabase authentication and access policies.",
    state: "Connect project",
  },
  {
    title: "Trusted telemetry",
    description: "Private events, signed ingestion, and audit collection.",
    state: "Connect source",
  },
  {
    title: "Behavioral detection",
    description: "Historical features and ML evaluation.",
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
  const [effectsEnabled, setEffectsEnabled] = useState(() =>
    typeof window.matchMedia === "function"
      ? !window.matchMedia("(prefers-reduced-motion: reduce)").matches
      : false,
  );
  const location = useLocation();
  const currentPage =
    navigation.find((item) => item.to === location.pathname)?.label ??
    {
      "/login": "Sign in",
      "/register": "Create account",
      "/forgot-password": "Account recovery",
      "/reset-password": "New password",
      "/auth/callback": "Confirm sign-in",
      "/admin": "Administrator access",
    }[location.pathname] ??
    "Page not found";
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
    document.title = `Sherlock Logs — ${currentPage}`;
  }, [location.pathname, currentPage]);
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
    <div className={`workspace ${effectsEnabled ? "effects-enabled" : ""}`}>
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
            <small>SIGNAL INTELLIGENCE</small>
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
          <span className="mono">TRUSTED TELEMETRY · STEP 04</span>
        </div>
      </aside>

      <div className="workspace-body">
        <header className="topbar">
          <div>
            <span className="breadcrumb-muted">Workspace</span>
            <ChevronRight size={14} aria-hidden="true" />
            <span>{currentPage}</span>
          </div>
          <div className="topbar-actions">
            <CommandMenu items={navigation} />
            <button
              className="effects-toggle"
              aria-label="Ambient effects"
              aria-pressed={effectsEnabled}
              onClick={() => setEffectsEnabled((enabled) => !enabled)}
              title="Toggle decorative animation"
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>Effects {effectsEnabled ? "on" : "off"}</span>
            </button>
            <span className="environment">
              <span />
              Local development
            </span>
          </div>
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
                    TRUSTED TELEMETRY
                  </div>
                  <div className="hero">
                    <div className="hero-copy">
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
                      <div className="hero-actions">
                        <Button asChild>
                          <Link to="/login">
                            Open sign-in
                            <ArrowRight size={16} aria-hidden="true" />
                          </Link>
                        </Button>
                        <Button variant="ghost" asChild>
                          <Link to="/architecture">
                            View architecture
                            <ArrowUpRight size={16} aria-hidden="true" />
                          </Link>
                        </Button>
                      </div>
                      <div className="hero-signature mono">
                        <span />
                        OBSERVE THE PATTERN. FOLLOW THE EVIDENCE.
                      </div>
                    </div>
                    <SignalVisual />
                  </div>

                  <div className="foundation-banner">
                    <span className="banner-icon">
                      <Check size={18} aria-hidden="true" />
                    </span>
                    <div>
                      <strong>The evidence pipeline is built.</strong>
                      <span>
                        Private event storage and trusted ingestion are ready
                        for database setup and source verification.
                      </span>
                    </div>
                    <Status tone="amber">Step 04</Status>
                  </div>

                  <div className="overview-grid">
                    <section
                      className="connection-section"
                      id="connection-overview"
                      tabIndex={-1}
                    >
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
                        A manual service check. Event collection coverage is
                        verified separately.
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
                            "Sign-in and permission checks are built. Connect a Supabase project to enable them.",
                        },
                        {
                          id: "database",
                          name: "Event storage",
                          icon: Database,
                          tag: "Not configured",
                          description:
                            "Private event storage and audit collection are built. Connect the database and verify your source.",
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
                        <article
                          className="panel integration-card"
                          data-integration={id}
                          key={id}
                        >
                          <div className="integration-top">
                            <Icon
                              size={23}
                              strokeWidth={1.5}
                              aria-hidden="true"
                            />
                            <span className="mono">
                              {id !== "detector"
                                ? "INTEGRATION BUILT"
                                : "UPCOMING"}
                            </span>
                          </div>
                          <h3>{name}</h3>
                          <p>
                            {current?.snapshot.integrations.find(
                              (item) => item.id === id,
                            )?.detail ?? description}
                          </p>
                          <Status>
                            {current?.snapshot.integrations.find(
                              (item) => item.id === id,
                            )?.status === "configured"
                              ? "Settings present"
                              : tag}
                          </Status>
                          <Link
                            className="integration-plan"
                            to="/architecture"
                            aria-label={`Integration plan for ${name}`}
                          >
                            Integration plan
                            <ArrowUpRight size={14} aria-hidden="true" />
                          </Link>
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
              path="/login"
              element={<AuthPage key="login" mode="login" />}
            />
            <Route
              path="/register"
              element={<AuthPage key="register" mode="register" />}
            />
            <Route
              path="/forgot-password"
              element={<AuthPage key="forgot" mode="forgot" />}
            />
            <Route
              path="/reset-password"
              element={<AuthPage key="reset" mode="reset" />}
            />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route path="/account" element={<ProtectedPage />} />
            <Route path="/admin" element={<ProtectedPage admin />} />
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
            text: "Private storage, signed ingestion, audit collection, and retention. Hosted coverage still needs verification.",
            state: "Setup required",
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
            declare its own login outcomes. Identity and event integration are
            built; project setup and live coverage checks remain. The audit
            collector covers successful logins; a failed-login publisher still
            needs connecting. Model training comes later.
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
        Use Node.js 22.12+ and Python 3.12+. The public workspace runs without
        Supabase. Create a Supabase project to enable account sign-in.
      </p>
      <div className="setup-grid">
        <section className="panel setup-card">
          <span className="step-number mono">IDENTITY & ACCESS</span>
          <h2>Connect Supabase</h2>
          <p>
            Create your development project, apply the identity SQL migration,
            then add the project URL and publishable key to the root{" "}
            <code>.env</code> file. Restart both services.
          </p>
          <a
            href={`${repository}/blob/main/supabase/README.md`}
            target="_blank"
            rel="noreferrer"
          >
            Follow the complete Supabase setup guide ↗
          </a>
        </section>
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
