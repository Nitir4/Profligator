import { FormEvent, useEffect, useState } from "react";
import arrowRightIcon from "./assets/login/arrow-right.svg";
import brandMarkIcon from "./assets/login/brand-mark.svg";
import cardMarkIcon from "./assets/login/card-mark.svg";
import emailIcon from "./assets/login/email.svg";
import eyeIcon from "./assets/login/eye.svg";
import googleIcon from "./assets/login/google.svg";
import helpIcon from "./assets/login/help.svg";
import lockIcon from "./assets/login/lock.svg";
import { ApiError, getCurrentUser, googleAuthError, loginCandidate, registerCandidate, requestPasswordReset, resetPassword, startGoogleAuth } from "./api";
import InformationPage, { informationTitles } from "./InformationPage";
import { VerifyEmailPage } from "./AccountVerification";
import AccountPage from "./AccountPage";
import DashboardPage from "./DashboardPage";
import ExtensionConnectPage from "./ExtensionConnectPage";
import IntegrationsPage from "./IntegrationsPage";
import ProfileSetupPage from "./ProfileSetupPage";
import PublicProfilePage from "./PublicProfilePage";
import SharingPage from "./SharingPage";
import TeamPage from "./TeamPage";
import WorkspaceAccess from "./WorkspaceAccess";

function App() {
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [path, setPath] = useState(window.location.pathname);
  const [authMode, setAuthMode] = useState<"login" | "register" | "forgot" | "reset">(
    window.location.pathname === "/forgot-password" ? "forgot" : window.location.pathname === "/reset-password" ? "reset" : "login");
  const [email, setEmail] = useState("");
  const [handle, setHandle] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [resetToken, setResetToken] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token") || "");
  const [authNotice, setAuthNotice] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(googleAuthError);
  const [submitting, setSubmitting] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [restoringSession, setRestoringSession] = useState(() => ["/", "/login"].includes(window.location.pathname));

  useEffect(() => {
    if (path !== "/" && path !== "/login") return;
    let active = true;
    setRestoringSession(true);
    getCurrentUser().then((user) => {
      if (active) window.location.replace(user.role === "recruiter" ? "/team" : "/dashboard");
    }).catch((failure: ApiError) => {
      if (!active) return;
      if (failure.status !== 401) setAuthError(failure.message);
      setRestoringSession(false);
    });
    return () => { active = false; };
  }, [path]);

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (path === "/forgot-password") setAuthMode("forgot");
    else if (path === "/reset-password") {
      setAuthMode("reset");
      if (window.location.hash) window.history.replaceState({}, "", "/reset-password");
    } else setAuthMode(current => current === "forgot" || current === "reset" ? "login" : current);
  }, [path]);

  useEffect(() => {
    document.title =
      path === "/verify-email" ? "Verify email | Profligator" : informationTitles[path] ? `${informationTitles[path]} | Profligator` : path.startsWith("/p/")
        ? "Shared profile | Profligator"
      : path === "/onboarding/profiles"
        ? "Connect coding profiles | Profligator"
        : path === "/dashboard"
          ? "Dashboard | Profligator"
          : path === "/integrations"
            ? "Integrations | Profligator"
          : path === "/team"
            ? "Team | Profligator"
          : path === "/extension" || path === "/extension/connect" || path === "/extension/duplicate-notification"
            ? "Browser extension | Profligator"
          : path === "/settings/account"
            ? "Account settings | Profligator"
          : path === "/settings/sharing"
            ? "Profile sharing | Profligator"
            : path === "/forgot-password" ? "Forgot password | Profligator"
            : path === "/reset-password" ? "Reset password | Profligator" : "Sign in | Profligator";
  }, [path]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setAuthError(null);
    setAuthNotice(null);
    try {
      if (authMode === "forgot") {
        const result = await requestPasswordReset(email);
        setAuthNotice(result.message);
        return;
      }
      if (authMode === "reset") {
        if (!resetToken) throw new Error("Open the complete reset link from your email, or request a new one.");
        if (password !== confirmPassword) throw new Error("Passwords do not match.");
        const result = await resetPassword(resetToken, password, confirmPassword);
        setPassword(""); setConfirmPassword(""); setResetToken("");
        setAuthNotice(result.message); setAuthMode("login");
        window.history.replaceState({}, "", "/login"); setPath("/login");
        return;
      }
      const session = authMode === "register"
        ? await registerCandidate(email, handle, password)
        : await loginCandidate(email, password);
      const next = session.user.role === "recruiter" ? "/team" : "/onboarding/profiles";
      window.history.pushState({}, "", next);
      setPath(next);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleGoogleSignIn() {
    setGoogleBusy(true);
    setAuthError(null);
    try { await startGoogleAuth(); }
    catch (error) {
      setAuthError(error instanceof Error ? error.message : "Google sign-in could not start.");
      setGoogleBusy(false);
    }
  }

  if (restoringSession && (path === "/" || path === "/login")) {
    return <div className="login-page"><main className="login-main"><p role="status">Restoring your session…</p></main></div>;
  }

  if (path === "/verify-email") return <WorkspaceAccess><VerifyEmailPage /></WorkspaceAccess>;

  if (informationTitles[path]) return <InformationPage path={path} />;

  if (path === "/onboarding/profiles") {
    return <WorkspaceAccess role="candidate"><ProfileSetupPage /></WorkspaceAccess>;
  }

  if (path.startsWith("/p/")) {
    return <PublicProfilePage token={path.slice(3)} />;
  }

  if (path === "/dashboard") {
    return <WorkspaceAccess role="candidate"><DashboardPage /></WorkspaceAccess>;
  }

  if (path === "/integrations") {
    return <WorkspaceAccess role="candidate"><IntegrationsPage /></WorkspaceAccess>;
  }

  if (path === "/team") {
    return <WorkspaceAccess><TeamPage /></WorkspaceAccess>;
  }

  if (path === "/settings/sharing") {
    return <WorkspaceAccess role="candidate"><SharingPage /></WorkspaceAccess>;
  }

  if (path === "/settings/account") {
    return <WorkspaceAccess><AccountPage /></WorkspaceAccess>;
  }

  if (path === "/extension" || path === "/extension/connect" || path === "/extension/duplicate-notification") {
    return <ExtensionConnectPage />;
  }

  return (
    <div className="login-page" data-node-id="2603:1408">
      <header className="product-header" data-node-id="2603:1409">
        <a className="brand" href="/dashboard" aria-label="Profligator home">
          <span className="brand-icon" aria-hidden="true">
            <img src={brandMarkIcon} alt="" />
          </span>
          <span>Profligator</span>
        </a>

        <div className="header-help">
          <span>Need help?</span>
          <a className="documentation-link" href="/documentation">
            <img src={helpIcon} alt="" />
            <span>Documentation</span>
          </a>
        </div>
      </header>

      <main className="login-main">
        <section
          className={`login-card ${authMode === "register" ? "register-mode" : ""} ${authMode === "forgot" || authMode === "reset" ? "recovery-mode" : ""} ${authError || authNotice ? "has-auth-error" : ""}`}
          aria-labelledby="login-title"
          data-node-id="2603:1427"
        >
          <div className="card-heading" data-node-id="2603:1429">
            <span className="card-mark" aria-hidden="true">
              <img src={cardMarkIcon} alt="" />
            </span>
            <h1 id="login-title">{authMode === "login" ? "Welcome back" : authMode === "register" ? "Create account" : authMode === "forgot" ? "Forgot password?" : "Reset password"}</h1>
            <p>
              {authMode === "login"
                ? "Sign in to access your unified coding statistics."
                : authMode === "register" ? "Create your candidate account to connect coding profiles."
                : authMode === "forgot" ? "Enter your account email to request a reset link."
                : "Choose a new password for your account."}
            </p>
          </div>

          <form className="login-form" onSubmit={handleSubmit} data-node-id="2603:1437">
            {authMode !== "reset" && <div className="field-group">
              <label htmlFor="email">Email address</label>
              <div className="input-shell">
                <span className="leading-icon" aria-hidden="true">
                  <img src={emailIcon} alt="" />
                </span>
                <input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
            </div>}

            {authMode === "register" && (
              <div className="field-group">
                <label htmlFor="handle">Candidate handle</label>
                <div className="input-shell">
                  <span className="leading-icon" aria-hidden="true">
                    <img src={emailIcon} alt="" />
                  </span>
                  <input
                    id="handle"
                    name="handle"
                    type="text"
                    autoComplete="username"
                    minLength={3}
                    value={handle}
                    onChange={(event) => setHandle(event.target.value)}
                  />
                </div>
              </div>
            )}

            {authMode !== "forgot" && <div className="field-group">
              <div className="field-label-row">
                <label htmlFor="password">Password</label>
                {authMode === "login" && <a href="/forgot-password">Forgot password?</a>}
              </div>
              <div className="input-shell">
                <span className="leading-icon lock-icon" aria-hidden="true">
                  <img src={lockIcon} alt="" />
                </span>
                <input
                  id="password"
                  name="password"
                  type={passwordVisible ? "text" : "password"}
                  autoComplete={authMode === "login" ? "current-password" : "new-password"}
                  minLength={authMode === "register" || authMode === "reset" ? 10 : undefined}
                  maxLength={128}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <button
                  className="password-toggle"
                  type="button"
                  aria-label={passwordVisible ? "Hide password" : "Show password"}
                  aria-pressed={passwordVisible}
                  onClick={() => setPasswordVisible((visible) => !visible)}
                >
                  <img src={eyeIcon} alt="" />
                </button>
              </div>
            </div>}

            {authMode === "reset" && <div className="field-group">
              <label htmlFor="confirm-password">Confirm password</label>
              <div className="input-shell">
                <span className="leading-icon lock-icon" aria-hidden="true"><img src={lockIcon} alt="" /></span>
                <input id="confirm-password" name="confirm-password" type={passwordVisible ? "text" : "password"}
                  autoComplete="new-password" minLength={10} maxLength={128} required value={confirmPassword}
                  onChange={event => setConfirmPassword(event.target.value)} />
              </div>
            </div>}

            {authError && <p className="auth-error" role="alert">{authError}</p>}
            {authNotice && <p className="auth-notice" role="status">{authNotice}</p>}

            <button className="sign-in-button" type="submit" disabled={submitting || googleBusy}>
              <span>
                {submitting
                  ? "Please wait…"
                  : authMode === "login"
                    ? "Sign In"
                    : authMode === "register" ? "Create Account" : authMode === "forgot" ? "Send reset link" : "Update password"}
              </span>
              <img src={arrowRightIcon} alt="" />
            </button>
          </form>

          {(authMode === "login" || authMode === "register") && <button className="google-button" type="button" data-node-id="2603:1469" disabled={submitting || googleBusy} onClick={handleGoogleSignIn}>
            <img src={googleIcon} alt="" />
            <span>{googleBusy ? "Opening Google…" : "Continue with Google"}</span>
          </button>}

          <div className="card-footer" data-node-id="2603:1477">
            <p>
              {authMode === "forgot" || authMode === "reset" ? <a className="auth-mode-link" href="/login">Back to sign in</a> : <><span>
                {authMode === "login" ? "Don't have an account?" : "Already have an account?"}
              </span>{" "}
              <button
                className="auth-mode-link"
                type="button"
                onClick={() => {
                  setAuthMode((current) => (current === "login" ? "register" : "login"));
                  setAuthError(null);
                  setAuthNotice(null);
                }}
              >
                {authMode === "login" ? "Create account" : "Sign in"}
              </button></>}
            </p>
          </div>
        </section>
      </main>

      <footer className="product-footer" data-node-id="2603:1481">
        <p>© 2026 Profligator Inc. All rights reserved.</p>
        <nav aria-label="Legal and support links">
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
          <a href="/status">Status</a>
          <a href="/support">Contact Support</a>
        </nav>
      </footer>
    </div>
  );
}

export default App;
