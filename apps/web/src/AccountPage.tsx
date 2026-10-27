import { useEffect, useState } from "react";
import { ApiError, AuthProviders, AuthUser, getAuthProviders, getCurrentUser, googleAuthError, startGoogleAuth } from "./api";
import SettingsLayout from "./SettingsLayout";
import AccountVerification from "./AccountVerification";
import googleIcon from "./assets/login/google.svg";
import ProfileEditor from "./ProfileEditor";

export default function AccountPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [providers, setProviders] = useState<AuthProviders | null>(null);
  const [error, setError] = useState<string | null>(googleAuthError);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getCurrentUser(), getAuthProviders()]).then(([account, auth]) => {
      if (active) { setUser(account); setProviders(auth); }
    }).catch((failure: ApiError) => {
      if (failure.status === 401) window.location.assign("/login");
      else if (active) setError(failure.message);
    });
    return () => { active = false; };
  }, []);

  async function connectGoogle() {
    setBusy(true);
    setError(null);
    try { await startGoogleAuth(true); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not connect Google."); setBusy(false); }
  }

  return <SettingsLayout user={user} active="account" title="Account settings" description="Your profile, sign-in methods and connected accounts.">
      {error && <p className="dashboard-api-error" role="alert">{error}</p>}
      {!providers ? <p role="status">Loading account…</p> : <>
      {user && <ProfileEditor user={user} onUpdated={setUser} />}
      <section className="settings-card" aria-labelledby="sign-in-title">
        <div className="settings-card-heading">
          <h2 id="sign-in-title">Sign-in methods</h2><p>Choose how you access your account.</p>
        </div>
        <div className="settings-row"><div><h3>Account email</h3><p>{user?.email}</p></div></div>
        <div className="settings-row"><div><h3>Password</h3><p>{providers.password_enabled ? "Sign in with your email and password." : "You currently sign in with Google."}</p></div><span className="settings-badge">{providers.password_enabled ? "Enabled" : "Not set"}</span></div>
        <div className="settings-row"><div className="settings-provider"><img src={googleIcon} alt="" /><div><h3>Google</h3><p>{providers.google_connected ? providers.google_email : "Use your Google account to sign in."}</p></div></div>
        {providers.google_connected ? <span className="settings-badge connected">Connected</span> : <>
          <button className="profile-detail-button" type="button" disabled={busy || !providers.google_configured} onClick={connectGoogle}>{busy ? "Opening Google…" : "Connect Google"}</button>
        </>}
        </div>
        {!providers.google_configured && !providers.google_connected && <p className="settings-note">Google sign-in is not available yet.</p>}
      </section>
        <AccountVerification showProfiles={user?.role === "candidate"} />
        {user?.role === "candidate" && <section className="settings-card"><div className="settings-row"><div><h2>Browser extension</h2><p>Import available history and check questions as you practice.</p></div><a className="profile-detail-button" href="/extension/connect">Manage browser connections</a></div></section>}
      </>}
  </SettingsLayout>;
}
