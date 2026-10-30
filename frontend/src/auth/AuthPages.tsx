import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  ArrowRight,
  Eye,
  EyeOff,
  Fingerprint,
  KeyRound,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { Button } from "../components/ui/button";
import {
  AccessError,
  authenticatedRequest,
  fetchIdentity,
  type Identity,
} from "../lib/api";
import { useAuth } from "./AuthProvider";

export function AuthSetupNotice() {
  const { error } = useAuth();
  return (
    <div className="auth-notice" role="status">
      <KeyRound size={20} aria-hidden="true" />
      <div>
        <strong>Connect Supabase to unlock sign-in.</strong>
        <p>
          {error ??
            "Your account pages are ready. Add your project URL and publishable key, then apply the database migration."}
        </p>
        <a
          href="https://github.com/Mamdouhelzein/sherlock-logs/blob/main/supabase/README.md"
          target="_blank"
          rel="noreferrer"
        >
          Open the Supabase setup guide ↗
        </a>
      </div>
    </div>
  );
}

function PasswordField({ minimum = 1 }: { minimum?: number }) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="form-field">
      <label htmlFor="password">Password</label>
      <div className="password-field">
        <input
          id="password"
          name="password"
          type={visible ? "text" : "password"}
          required
          minLength={minimum}
          maxLength={128}
          autoComplete={minimum > 1 ? "new-password" : "current-password"}
          aria-describedby={minimum > 1 ? "password-help" : undefined}
        />
        <button
          type="button"
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          onClick={() => setVisible(!visible)}
        >
          {visible ? (
            <EyeOff size={18} aria-hidden="true" />
          ) : (
            <Eye size={18} aria-hidden="true" />
          )}
        </button>
      </div>
      {minimum > 1 && (
        <small id="password-help">
          Use 12–128 characters. A long, unique passphrase works well.
        </small>
      )}
    </div>
  );
}

type Mode = "login" | "register" | "forgot" | "reset";
const copy = {
  login: {
    title: "Welcome back, detective.",
    description: "Sign in to your private workspace and pick up the case.",
    action: "Sign in",
  },
  register: {
    title: "Your first case starts here.",
    description: "Create your account. Your profile is private by default.",
    action: "Create account",
  },
  forgot: {
    title: "Lost your way in?",
    description: "We’ll send a secure recovery link to your email.",
    action: "Send recovery link",
  },
  reset: {
    title: "A fresh key to the case.",
    description: "Choose a new password for your account.",
    action: "Update password",
  },
};

export function AuthPage({ mode }: { mode: Mode }) {
  const { client, session, loading, error: sessionError } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  if (loading) return <Pending text="Restoring your session…" />;
  if (session && (mode === "login" || mode === "register"))
    return <Navigate to="/account" replace />;
  const { title, description, action } = copy[mode];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!client || busy) return;
    const values = new FormData(event.currentTarget);
    const email = String(values.get("email") ?? "").trim();
    const password = String(values.get("password") ?? "");
    setError("");
    setNotice("");
    setBusy(true);
    try {
      if (mode === "login") {
        const result = await client.auth.signInWithPassword({
          email,
          password,
        });
        if (result.error)
          throw new Error(
            result.error.status === 429
              ? "Too many attempts. Please wait before trying again."
              : "Sign-in failed. Check your email and password, and confirm your email if needed.",
          );
        navigate("/account", { replace: true });
      } else if (mode === "register") {
        const result = await client.auth.signUp({
          email,
          password,
          options: {
            data: {
              display_name: String(values.get("display_name") ?? "").trim(),
            },
            emailRedirectTo: `${window.location.origin}/auth/callback`,
          },
        });
        if (result.error)
          throw new Error(
            "Unable to create your account. Check the password requirements or try again shortly.",
          );
        if (result.data.session) navigate("/account", { replace: true });
        else
          setNotice(
            "Check your inbox for a confirmation link. If this address already has an account, sign in or reset its password. Open the link in this browser.",
          );
      } else if (mode === "forgot") {
        const result = await client.auth.resetPasswordForEmail(email, {
          redirectTo: `${window.location.origin}/reset-password`,
        });
        if (result.error)
          throw new Error(
            "The recovery request could not be sent. Please wait and try again.",
          );
        setNotice(
          "If an account exists for this email, a recovery link is on its way. Open it in this browser.",
        );
      } else {
        const result = await client.auth.updateUser({ password });
        if (result.error)
          throw new Error(
            "Unable to update your password. Request a fresh recovery link and try again.",
          );
        setNotice("Password updated. You can return to your account.");
      }
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The request failed. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-layout">
      <section className="auth-intro">
        <div className="page-label mono">IDENTITY & ACCESS · STEP 03</div>
        <span className="auth-emblem">
          <Fingerprint size={38} strokeWidth={1.3} aria-hidden="true" />
        </span>
        <h1>{title}</h1>
        <p>{description}</p>
        <div className="auth-promise">
          <ShieldCheck size={19} aria-hidden="true" />
          <span>
            Private profiles. Explicit permissions.
            <br />
            Evidence starts with trusted identity.
          </span>
        </div>
      </section>
      <section className="panel auth-card" aria-label={action}>
        <span className="mono auth-card-label">THE ACCESS DESK</span>
        <h2>
          {mode === "register"
            ? "Create your account"
            : mode === "login"
              ? "Account sign-in"
              : "Account recovery"}
        </h2>
        {!client && <AuthSetupNotice />}
        {sessionError && client && (
          <p className="form-error" role="alert">
            {sessionError}
          </p>
        )}
        {mode === "reset" && !session && client && (
          <p role="alert" className="form-error">
            Open a valid recovery link in the browser where you requested it, or
            request a new one below.
          </p>
        )}
        <form onSubmit={(event) => void submit(event)}>
          <fieldset
            disabled={!client || busy || (mode === "reset" && !session)}
          >
            {mode === "register" && (
              <div className="form-field">
                <label htmlFor="display-name">Display name</label>
                <input
                  id="display-name"
                  name="display_name"
                  autoComplete="name"
                  maxLength={80}
                  required
                />
              </div>
            )}
            {mode !== "reset" && (
              <div className="form-field">
                <label htmlFor="email">Email address</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  maxLength={254}
                  required
                />
              </div>
            )}
            {mode !== "forgot" && (
              <PasswordField minimum={mode === "login" ? 1 : 12} />
            )}
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
            {notice && (
              <p className="form-notice" role="status">
                {notice}
              </p>
            )}
            <Button type="submit" className="auth-submit">
              {busy ? "Please wait…" : action}
              <ArrowRight size={16} aria-hidden="true" />
            </Button>
          </fieldset>
        </form>
        <div className="auth-links">
          {mode === "login" ? (
            <>
              <Link to="/register">Create an account</Link>
              <Link to="/forgot-password">Forgot password?</Link>
            </>
          ) : (
            <Link to="/login">Back to sign-in</Link>
          )}
          {mode === "reset" && (
            <Link to="/forgot-password">Request a new recovery link</Link>
          )}
          {notice && mode === "reset" && (
            <Link to="/account">Go to your account</Link>
          )}
        </div>
      </section>
    </div>
  );
}

export function Pending({ text }: { text: string }) {
  return (
    <div className="document-page">
      <p role="status">{text}</p>
    </div>
  );
}

export function AuthCallback() {
  const { loading, session, client, error } = useAuth();
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  if (!client) return <AuthSetupNotice />;
  if (loading) return <Pending text="Verifying your sign-in link…" />;
  if (session && !params.has("error"))
    return <Navigate to="/account" replace />;
  return (
    <div className="document-page">
      <h1>This link needs another look.</h1>
      <p role="alert">
        {error ??
          "The link may have expired, already been used, or been opened in a different browser."}
      </p>
      <Link to="/login">Return to sign-in</Link>
    </div>
  );
}

export function ProtectedPage({ admin = false }: { admin?: boolean }) {
  const { session, loading, client } = useAuth();
  const identity = useQuery({
    queryKey: ["identity", session?.user.id, session?.expires_at],
    queryFn: async ({ signal }) => {
      const result = await fetchIdentity(session!.access_token, signal);
      if (result.id !== session!.user.id)
        throw new Error(
          "The verified identity does not match this session. Sign out and try again.",
        );
      return result;
    },
    enabled: Boolean(session),
    retry: false,
    staleTime: 0,
    meta: { private: true },
  });
  if (loading) return <Pending text="Restoring your session…" />;
  if (!client)
    return (
      <div className="document-page">
        <h1>Your private workspace.</h1>
        <AuthSetupNotice />
        <Link to="/login">Open sign-in</Link>
      </div>
    );
  if (!session) return <Navigate to="/login" replace />;
  if (identity.isPending)
    return <Pending text="Checking your identity with the server…" />;
  if (identity.isError)
    return (
      <AccessFailure
        error={identity.error}
        retry={() => void identity.refetch()}
      />
    );
  if (admin && identity.data.role !== "admin")
    return (
      <div className="document-page">
        <h1>Administrator access required.</h1>
        <p>
          Your account is a member. A project administrator must grant access
          through the database.
        </p>
        <Link to="/account">Return to your account</Link>
      </div>
    );
  return admin ? (
    <AdminPage identity={identity.data} token={session.access_token} />
  ) : (
    <AccountPage identity={identity.data} />
  );
}

function AccessFailure({ error, retry }: { error: Error; retry: () => void }) {
  return (
    <div className="document-page">
      <h1>Access needs attention.</h1>
      <p role="alert">{error.message}</p>
      {error instanceof AccessError && error.status === 401 ? (
        <Link to="/account">Return to your account to sign out</Link>
      ) : (
        <Button variant="outline" onClick={retry}>
          Try verification again
        </Button>
      )}
      <SignOut />
    </div>
  );
}

function SignOut() {
  const { client } = useAuth();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function signOut() {
    if (!client) return;
    setBusy(true);
    setError("");
    try {
      const result = await client.auth.signOut({ scope: "local" });
      if (result.error) throw result.error;
      queryClient.removeQueries({
        predicate: (query) => query.meta?.private === true,
      });
      navigate("/login", { replace: true });
    } catch {
      setError(
        "Sign-out could not complete. Check your connection and try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="sign-out">
      <Button variant="outline" onClick={() => void signOut()} disabled={busy}>
        {busy ? "Signing out…" : "Sign out"}
      </Button>
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
    </div>
  );
}

function AccountPage({ identity }: { identity: Identity }) {
  const { client } = useAuth();
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const profile = useQuery({
    queryKey: ["profile", identity.id],
    meta: { private: true },
    queryFn: async () => {
      const { data, error } = await client!
        .from("profiles")
        .select("display_name")
        .eq("id", identity.id)
        .single();
      if (error)
        throw new Error(
          "Cannot load your profile. Check that the identity migration is applied.",
        );
      return data as { display_name: string };
    },
    retry: false,
  });
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage("");
    const display_name = String(
      new FormData(event.currentTarget).get("display_name") ?? "",
    ).trim();
    try {
      const { data, error } = await client!
        .from("profiles")
        .update({ display_name })
        .eq("id", identity.id)
        .select("display_name")
        .single();
      if (error || !data) throw new Error();
      await profile.refetch();
      setMessage("Profile saved.");
    } catch {
      setMessage("Unable to save your profile. Try again shortly.");
    } finally {
      setSaving(false);
    }
  }
  return (
    <div className="document-page account-page">
      <div className="page-label mono">YOUR PRIVATE CASE FILE</div>
      <h1>Identity, verified.</h1>
      <p className="document-lead">
        Your session and permissions have been checked by the API.
      </p>
      <div className="account-grid">
        <section className="panel auth-card">
          <UserRound size={26} aria-hidden="true" />
          <h2>Your account</h2>
          <dl className="identity-details">
            <dt>Email</dt>
            <dd>{identity.email}</dd>
            <dt>Access level</dt>
            <dd className="role-label">{identity.role}</dd>
          </dl>
          {profile.isPending ? (
            <p role="status">Loading profile…</p>
          ) : profile.isError ? (
            <>
              <p role="alert">{profile.error.message}</p>
              <Button variant="outline" onClick={() => void profile.refetch()}>
                Retry profile
              </Button>
            </>
          ) : (
            <form
              key={profile.data.display_name}
              onSubmit={(event) => void save(event)}
            >
              <div className="form-field">
                <label htmlFor="profile-name">Display name</label>
                <input
                  id="profile-name"
                  name="display_name"
                  maxLength={80}
                  defaultValue={profile.data.display_name}
                />
              </div>
              <Button disabled={saving} type="submit">
                {saving ? "Saving…" : "Save profile"}
              </Button>
            </form>
          )}
          {message && <p role="status">{message}</p>}
          <SignOut />
        </section>
        <section className="panel auth-card">
          <ShieldCheck size={26} aria-hidden="true" />
          <h2>Permissions with a purpose.</h2>
          <p>
            Members manage their own profile. Administrator permissions are
            assigned in the database, and checked on every protected API
            request.
          </p>
          <Link to="/admin">Check administrator access →</Link>
          <p className="section-footnote">
            Login telemetry and ML detection are upcoming milestones.
          </p>
        </section>
      </div>
    </div>
  );
}

function AdminPage({ identity, token }: { identity: Identity; token: string }) {
  const authorization = useQuery({
    queryKey: ["admin-status", identity.id],
    meta: { private: true },
    staleTime: 0,
    retry: false,
    queryFn: async ({ signal }) => {
      const value = await authenticatedRequest("/admin/status", token, signal);
      if (value.status !== "authorized" || value.user_id !== identity.id)
        throw new Error("Unexpected authorization response.");
      return value;
    },
  });
  if (authorization.isPending)
    return <Pending text="Verifying administrator permissions…" />;
  if (authorization.isError)
    return (
      <AccessFailure
        error={authorization.error}
        retry={() => void authorization.refetch()}
      />
    );
  return (
    <div className="document-page">
      <div className="page-label mono">RESTRICTED ACCESS</div>
      <h1>Administrator access confirmed.</h1>
      <div className="boundary-note">
        <ShieldCheck size={26} aria-hidden="true" />
        <p>
          The API has authorized this account as an administrator. Event
          ingestion, detection, and investigation tools will be added in later
          milestones.
        </p>
      </div>
      <Link to="/account">Return to your account</Link>
    </div>
  );
}
