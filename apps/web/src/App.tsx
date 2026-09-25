import { FormEvent, useEffect, useState } from "react";
import arrowRightIcon from "./assets/login/arrow-right.svg";
import brandMarkIcon from "./assets/login/brand-mark.svg";
import cardMarkIcon from "./assets/login/card-mark.svg";
import emailIcon from "./assets/login/email.svg";
import eyeIcon from "./assets/login/eye.svg";
import googleIcon from "./assets/login/google.svg";
import helpIcon from "./assets/login/help.svg";
import lockIcon from "./assets/login/lock.svg";
import DashboardPage from "./DashboardPage";
import ExtensionNotificationPage from "./ExtensionNotificationPage";
import ProfileSetupPage from "./ProfileSetupPage";
import SharingPage from "./SharingPage";

function App() {
  const [passwordVisible, setPasswordVisible] = useState(true);
  const [path, setPath] = useState(window.location.pathname);

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
          : path === "/extension" || path === "/extension/duplicate-notification"
            ? "Duplicate problem detected | Profligator"
          : path === "/settings/sharing"
            ? "Profile sharing | Profligator"
            : "Sign in | Profligator";
  }, [path]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    window.history.pushState({}, "", "/onboarding/profiles");
    setPath("/onboarding/profiles");
  }

  if (path === "/onboarding/profiles") {
    return <ProfileSetupPage />;
  }

  if (path === "/dashboard") {
    return <DashboardPage />;
  }

  if (path === "/settings/sharing") {
    return <SharingPage />;
  }

  if (path === "/extension" || path === "/extension/duplicate-notification") {
    return <ExtensionNotificationPage />;
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
        <section className="login-card" aria-labelledby="login-title" data-node-id="2603:1427">
          <div className="card-heading" data-node-id="2603:1429">
            <span className="card-mark" aria-hidden="true">
              <img src={cardMarkIcon} alt="" />
            </span>
            <h1 id="login-title">Welcome back</h1>
            <p>Sign in to access your unified coding statistics.</p>
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
                  defaultValue="alex@example.com"
                />
              </div>
            </div>

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
                  defaultValue="secretpassword123"
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

            <button className="sign-in-button" type="submit">
              <span>Sign In</span>
              <img src={arrowRightIcon} alt="" />
            </button>
          </form>

          <button className="google-button" type="button" data-node-id="2603:1469">
            <img src={googleIcon} alt="" />
            <span>Continue with Google</span>
          </button>

          <div className="card-footer" data-node-id="2603:1477">
            <p>
              <span>Don&apos;t have an account?</span>{" "}
              <a href="#create-account">Create account</a>
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
