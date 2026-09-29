import { FormEvent, useEffect, useState } from "react";
import arrowRightIcon from "./assets/login/arrow-right.svg";
import brandMarkIcon from "./assets/login/brand-mark.svg";
import cardMarkIcon from "./assets/login/card-mark.svg";
import emailIcon from "./assets/login/email.svg";
import eyeIcon from "./assets/login/eye.svg";
import googleIcon from "./assets/login/google.svg";
import helpIcon from "./assets/login/help.svg";
import lockIcon from "./assets/login/lock.svg";
import { loginCandidate, registerCandidate } from "./api";
import DashboardPage from "./DashboardPage";
<<<<<<< HEAD
import ExtensionNotificationPage from "./ExtensionNotificationPage";
import IntegrationsPage from "./IntegrationsPage";
=======
>>>>>>> parent of cdbf240 (feat(web): implement extension duplicate notification screen)
import ProfileSetupPage from "./ProfileSetupPage";
import SharingPage from "./SharingPage";
import TeamPage from "./TeamPage";

function App() {
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [path, setPath] = useState(window.location.pathname);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [handle, setHandle] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname);
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    document.title =
      path === "/onboarding/profiles"
        ? "Connect coding profiles | Profligator"
        : path === "/dashboard"
          ? "Dashboard | Profligator"
<<<<<<< HEAD
          : path === "/integrations"
            ? "Integrations | Profligator"
          : path === "/team"
            ? "Team | Profligator"
          : path === "/extension" || path === "/extension/duplicate-notification"
            ? "Duplicate problem detected | Profligator"
=======
>>>>>>> parent of cdbf240 (feat(web): implement extension duplicate notification screen)
          : path === "/settings/sharing"
            ? "Profile sharing | Profligator"
            : "Sign in | Profligator";
  }, [path]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setAuthError(null);
    try {
      if (authMode === "register") {
        await registerCandidate(email, handle, password);
      } else {
        await loginCandidate(email, password);
      }
      window.history.pushState({}, "", "/onboarding/profiles");
      setPath("/onboarding/profiles");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Authentication failed.");
    } finally {
      setSubmitting(false);
    }
  }

  if (path === "/onboarding/profiles") {
    return <ProfileSetupPage />;
  }

  if (path === "/dashboard") {
    return <DashboardPage />;
  }

  if (path === "/integrations") {
    return <IntegrationsPage />;
  }

  if (path === "/team") {
    return <TeamPage />;
  }

  if (path === "/settings/sharing") {
    return <SharingPage />;
  }

  return (
    <div className="login-page" data-node-id="2603:1408">
      <header className="product-header" data-node-id="2603:1409">
        <a className="brand" href="#" aria-label="Profligator home">
          <span className="brand-icon" aria-hidden="true">
            <img src={brandMarkIcon} alt="" />
          </span>
          <span>Profligator</span>
        </a>

        <div className="header-help">
          <span>Need help?</span>
          <a className="documentation-link" href="#documentation">
            <img src={helpIcon} alt="" />
            <span>Documentation</span>
          </a>
        </div>
      </header>

      <main className="login-main">
        <section
          className={`login-card ${authMode === "register" ? "register-mode" : ""} ${authError ? "has-auth-error" : ""}`}
          aria-labelledby="login-title"
          data-node-id="2603:1427"
        >
          <div className="card-heading" data-node-id="2603:1429">
            <span className="card-mark" aria-hidden="true">
              <img src={cardMarkIcon} alt="" />
            </span>
            <h1 id="login-title">{authMode === "login" ? "Welcome back" : "Create account"}</h1>
            <p>
              {authMode === "login"
                ? "Sign in to access your unified coding statistics."
                : "Create your candidate account to connect coding profiles."}
            </p>
          </div>

          <form className="login-form" onSubmit={handleSubmit} data-node-id="2603:1437">
            <div className="field-group">
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
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </div>
            </div>

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

            <div className="field-group">
              <div className="field-label-row">
                <label htmlFor="password">Password</label>
                <a href="#forgot-password">Forgot password?</a>
              </div>
              <div className="input-shell">
                <span className="leading-icon lock-icon" aria-hidden="true">
                  <img src={lockIcon} alt="" />
                </span>
                <input
                  id="password"
                  name="password"
                  type={passwordVisible ? "text" : "password"}
                  autoComplete="current-password"
                  minLength={authMode === "register" ? 10 : undefined}
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
            </div>

            {authError && <p className="auth-error" role="alert">{authError}</p>}

            <button className="sign-in-button" type="submit" disabled={submitting}>
              <span>
                {submitting
                  ? "Please wait…"
                  : authMode === "login"
                    ? "Sign In"
                    : "Create Account"}
              </span>
              <img src={arrowRightIcon} alt="" />
            </button>
          </form>

          <button className="google-button" type="button" data-node-id="2603:1469" disabled>
            <img src={googleIcon} alt="" />
            <span>Continue with Google</span>
          </button>

          <div className="card-footer" data-node-id="2603:1477">
            <p>
              <span>
                {authMode === "login" ? "Don't have an account?" : "Already have an account?"}
              </span>{" "}
              <button
                className="auth-mode-link"
                type="button"
                onClick={() => {
                  setAuthMode((current) => (current === "login" ? "register" : "login"));
                  setAuthError(null);
                }}
              >
                {authMode === "login" ? "Create account" : "Sign in"}
              </button>
            </p>
          </div>
        </section>
      </main>

      <footer className="product-footer" data-node-id="2603:1481">
        <p>© 2026 Profligator Inc. All rights reserved.</p>
        <nav aria-label="Legal and support links">
          <a href="#privacy">Privacy</a>
          <a href="#terms">Terms</a>
          <a href="#status">Status</a>
          <a href="#support">Contact Support</a>
        </nav>
      </footer>
    </div>
  );
}

export default App;
