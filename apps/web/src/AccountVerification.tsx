import { useEffect, useState } from "react";
import { confirmEmailVerification, confirmProfileOwnership, getVerificationStatus, listPlatformProfiles, OwnershipChallenge, PlatformProfile, requestEmailVerification, requestOwnershipChallenge, VerificationStatus } from "./api";

export default function AccountVerification({ showProfiles = true }: { showProfiles?: boolean }) {
  const [status, setStatus] = useState<VerificationStatus | null>(null);
  const [profiles, setProfiles] = useState<PlatformProfile[]>([]);
  const [challenges, setChallenges] = useState<Record<string, OwnershipChallenge>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    Promise.all([getVerificationStatus(), showProfiles ? listPlatformProfiles() : Promise.resolve([])]).then(([verification, linked]) => {
      if (active) { setStatus(verification); setProfiles(linked); }
    }).catch(failure => { if (active) setError(failure.message); });
    return () => { active = false; };
  }, [showProfiles]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); } catch (failure) { setError(failure instanceof Error ? failure.message : "Verification failed."); }
    finally { setBusy(false); }
  }
  return <div className="settings-verification" aria-label="Account and profile verification">
    <section className="settings-card" aria-labelledby="email-verification-title">
    <div className="settings-card-heading"><h2 id="email-verification-title">Email verification</h2><p>Confirm the inbox you use for your Profligator account.</p></div>
    {status ? <>
      <div className="settings-row"><div><h3>{status.email}</h3><p>{status.email_verified ? "Your email address is confirmed." : "Check your inbox after requesting a verification link."}</p></div>
      <span className={`settings-badge${status.email_verified ? " connected" : ""}`}>{status.email_verified ? "Verified" : "Not verified"}</span></div>
      {!status.email_verified && <button type="button" className="profile-detail-button" disabled={busy || !status.email_delivery_configured}
        onClick={() => perform(async () => { setMessage((await requestEmailVerification()).message); })}>Send verification email</button>}
      {!status.email_delivery_configured && <p>Verification email delivery has not been configured yet.</p>}
    </> : <p>Loading verification status…</p>}
    </section>
    {showProfiles && <section className="settings-card" aria-labelledby="ownership-title">
    <div className="settings-card-heading"><h2 id="ownership-title">Coding-profile ownership</h2><p>Confirm that you control each connected profile.</p></div>
    <details className="coverage-details"><summary>How ownership verification works</summary><p>Verify your app email, then temporarily add a one-use challenge to the coding platform's public name. Its account email may differ from your Profligator email. Linking a public profile alone does not prove ownership.</p></details>
    {profiles.length === 0 && <p className="settings-note">No linked profiles yet. <a href="/onboarding/profiles">Add a coding profile</a>.</p>}
    {profiles.map(profile => <div key={profile.id} className="ownership-profile">
      <h3>{profile.platform} · {profile.public_handle}</h3>
      <p>Ownership: {profile.verification_state === "verified" ? "Verified" : profile.verification_state === "fixture_only" ? "Fixture data — cannot verify ownership" : "Not verified"}</p>
      {profile.verification_state !== "verified" && profile.verification_state !== "fixture_only" && <>
        <button type="button" className="profile-detail-button" disabled={busy || !status?.email_verified}
          onClick={() => perform(async () => { const challenge = await requestOwnershipChallenge(profile.id); setChallenges(current => ({ ...current, [profile.id]: challenge })); })}>Create ownership challenge</button>
        {challenges[profile.id] && <>
          <p>{challenges[profile.id].instructions} The challenge expires in {challenges[profile.id].expires_in_minutes} minutes.</p>
          <p><code className="ownership-challenge">{challenges[profile.id].challenge}</code></p>
          <p><a href={profile.canonical_url} target="_blank" rel="noopener noreferrer">Open your coding profile</a></p>
          <button type="button" className="profile-detail-button" disabled={busy} onClick={() => perform(async () => {
            setMessage((await confirmProfileOwnership(profile.id, challenges[profile.id].challenge)).message);
            setProfiles(await listPlatformProfiles());
          })}>Check public profile name</button>
        </>}
      </>}
    </div>)}
    </section>}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
  </div>;
}

export function VerifyEmailPage() {
  const [token] = useState(() => new URLSearchParams(window.location.hash.slice(1)).get("token") || "");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { window.history.replaceState({}, "", "/verify-email"); }, []);
  async function confirm() {
    setBusy(true); setError("");
    try { setMessage((await confirmEmailVerification(token)).message); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Verification failed."); }
    finally { setBusy(false); }
  }
  return <main className="dashboard-main"><div className="dashboard-content information-content">
    <h1>Verify your email</h1>
    <p>Confirm this link while signed in to the account that requested it.</p>
    {!message && <button className="profile-detail-button" disabled={busy || !token} onClick={confirm}>Verify email</button>}
    {!token && <p role="alert">Open the complete link from your email. If you signed in on the way here, reopen the email link after signing in.</p>}
    {message && <p role="status">{message}</p>}{error && <p role="alert">{error}</p>}
    <p><a href="/settings/account">Return to account settings</a></p>
  </div></main>;
}
