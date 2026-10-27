import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, AuthUser, ExtensionSession, getCurrentUser, getExtensionSessions, revokeExtensionSession } from "./api";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

export default function ExtensionConnectPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [devices, setDevices] = useState<ExtensionSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [available, setAvailable] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [firefoxInstallAvailable, setFirefoxInstallAvailable] = useState(false);
  const pending = useRef<string | null>(null);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const account = await getCurrentUser();
      setUser(account);
      setDevices(account.role === "candidate" ? await getExtensionSessions() : []);
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 401) { setUser(null); setDevices([]); }
      else setError(failure instanceof Error ? failure.message : "Could not load your account.");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/downloads/profligator-firefox.xpi", { method: "HEAD", signal: controller.signal })
      .then((response) => setFirefoxInstallAvailable(response.ok &&
        response.headers.get("Content-Type")?.split(";")[0].trim() === "application/x-xpinstall"))
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    void refresh();
    const pingId = crypto.randomUUID();
    const ping = () => window.postMessage({ source: "profligator-app", type: "PF_PING", requestId: pingId }, location.origin);
    const interval = setInterval(ping, 1000);
    function receive(event: MessageEvent) {
      if (event.source !== window || event.origin !== location.origin || event.data?.source !== "profligator-extension") return;
      if (event.data.requestId === pingId && event.data.available === true) { setAvailable(true); clearInterval(interval); }
      if (pending.current && event.data.requestId === pending.current) {
        pending.current = null;
        if (timeout.current) clearTimeout(timeout.current);
        setBusy(false);
        if (event.data.connected === true) { setConnected(true); void refresh(); }
        else setError(typeof event.data.error === "string" ? event.data.error : "Could not connect this browser.");
      }
    }
    window.addEventListener("message", receive);
    window.addEventListener("focus", refresh);
    ping();
    return () => {
      clearInterval(interval);
      if (timeout.current) clearTimeout(timeout.current);
      window.removeEventListener("message", receive);
      window.removeEventListener("focus", refresh);
    };
  }, [refresh]);

  function connect() {
    setBusy(true); setError(null); setConnected(false);
    pending.current = crypto.randomUUID();
    window.postMessage({ source: "profligator-app", type: "PF_AUTHORIZE", requestId: pending.current }, location.origin);
    timeout.current = setTimeout(() => {
      pending.current = null; setBusy(false); setError("The extension did not respond. Check the app connection and try again.");
    }, 30000);
  }

  async function revoke(id: string) {
    setError(null);
    try {
      await revokeExtensionSession(id); setConnected(false); await refresh();
      window.postMessage({ source: "profligator-app", type: "PF_REVOKED", requestId: crypto.randomUUID() }, location.origin);
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not revoke the connection."); }
  }

  return <div className="dashboard-page">
    <WorkspaceHeader user={user} activeTab="account" />
    <main className="dashboard-main"><div className="dashboard-content extension-connect-content">
      <h1>Connect your browser</h1>
      <p>Check LeetCode, GeeksforGeeks and Codeforces questions against your imported history while you practice.</p>
      {error && <p className="dashboard-api-error" role="alert">{error}</p>}
      <section className="profile-detail-card">
        <h2>Profligator extension</h2>
        <p><a href="/downloads/profligator-chrome.zip">Download for Chrome / Chromium</a> · {firefoxInstallAvailable
          ? <a href="/downloads/profligator-firefox.xpi">Install for Firefox</a>
          : <a href="/downloads/profligator-firefox.zip">Download for Firefox (temporary)</a>}</p>
        {firefoxInstallAvailable
          ? <p>Firefox: open the install link and approve the browser prompt. The signed extension stays installed after restarting Firefox.</p>
          : <p>Permanent Firefox installation is awaiting Mozilla signing. The test download lasts until Firefox closes.</p>}
        <details className="coverage-details"><summary>Installation steps</summary>
          <p>Chrome: extract the ZIP, open chrome://extensions, enable Developer mode, and choose Load unpacked. Select the folder containing manifest.json.</p>
          {!firefoxInstallAvailable && <p>Firefox test installation: extract the ZIP, open about:debugging, select This Firefox, then Load Temporary Add-on and choose manifest.json.</p>}
        </details>
        <p role="status">{available ? "The extension is available in this browser." : "Install and enable the extension, then reload this page."}</p>
        {loading ? <p>Loading your account…</p> : !user ? <>
          <p>Sign in with your existing Google or password account, then return to this tab.</p>
          <a className="profile-detail-button" href="/login" target="_blank" rel="noopener noreferrer">Sign in to Profligator</a>
          <button className="profile-detail-button" type="button" onClick={() => void refresh()}>I’ve signed in — refresh</button>
        </> : user.role !== "candidate" ? <p>The extension requires a candidate account.</p> : <>
          <p>Signed in as <strong>{user.handle}</strong>. Connecting lets this browser check and import solved questions for your linked accounts, and save public question text for questions already in your solved history. You can enable acceptance tracking separately in the extension popup.</p>
          <button className="profile-detail-button" type="button" disabled={!available || busy} onClick={connect}>{busy ? "Connecting…" : "Connect this browser"}</button>
          {connected && <p role="status">Browser connected. Open a supported question to see its history check.</p>}
        </>}
        <p>Checks currently cover known solved questions and exact statement matches. Similarity matching will follow after model evaluation.</p>
        <p>Use “Import solved history” in the extension popup for LeetCode, GeeksforGeeks and Codeforces. LeetCode uses your signed-in browser tab; available acceptance dates are imported without guessing missing dates or time zones.</p>
        <p>Repeated LeetCode imports continue checking older Accepted submissions. For saved GFG and Codeforces questions, opening their problem pages can fill missing question text. Visiting a question never marks it solved.</p>
      </section>
      {user?.role === "candidate" && <section className="profile-detail-card">
        <h2>Browser connections</h2>
        {!devices.length ? <p>No active connections.</p> : <ul className="extension-connections">{devices.map((device) => <li key={device.id}>
          <div><strong>{device.label}</strong><p>Connected {new Date(device.created_at).toLocaleString()} · Expires {new Date(device.expires_at).toLocaleDateString()}</p></div>
          <button className="profile-detail-button" type="button" onClick={() => void revoke(device.id)}>Revoke connection</button>
        </li>)}</ul>}
      </section>}
    </div></main><WorkspaceFooter />
  </div>;
}
