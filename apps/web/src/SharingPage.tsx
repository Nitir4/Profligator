import { useEffect, useState } from "react";
import { ApiError, AuthUser, getCurrentUser, getSharing, updateSharing } from "./api";
import SettingsLayout from "./SettingsLayout";
import copyIcon from "./assets/sharing/copy.svg";
import linkIcon from "./assets/sharing/link.svg";
import lockIcon from "./assets/sharing/lock.svg";

function SharingPage() {
  const [sharingEnabled, setSharingEnabled] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getCurrentUser(), getSharing()]).then(([account, sharing]) => {
      if (!active) return;
      setUser(account);
      setSharingEnabled(sharing.enabled);
      setShareUrl(sharing.shareable_link);
    }).catch((err: ApiError) => {
      if (err.status === 401) window.location.assign("/login");
      if (active) setError(err.message);
    }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, []);

  async function toggleSharing() {
    setBusy(true);
    setError(null);
    try {
      const sharing = await updateSharing(!sharingEnabled);
      setSharingEnabled(sharing.enabled);
      setShareUrl(sharing.shareable_link);
      setCopied(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update sharing.");
    } finally { setBusy(false); }
  }

  async function copyShareLink() {
    if (!shareUrl) return;
    try {
      await navigator.clipboard.writeText(shareUrl);
    } catch {
      setError("Could not copy the link. Select and copy it from the field.");
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <SettingsLayout user={user} active="sharing" title="Profile sharing" description="Choose whether others can view your coding portfolio.">
          <section className="settings-card" aria-labelledby="sharing-visibility-title">
            {error && <p className="auth-error" role="alert">{error}</p>}
            <div className="settings-row sharing-toggle-row">
              <div>
                <h2 id="sharing-visibility-title">{sharingEnabled ? "Anyone with the link" : "Your profile is private"}</h2>
                <p>{sharingEnabled ? "People with your link can view your imported statistics." : "Turn on sharing to create a link you can send to others."}</p>
              </div>
              <button
                className={`sharing-switch${sharingEnabled ? " enabled" : ""}`}
                type="button"
                role="switch"
                aria-checked={sharingEnabled}
                aria-label="Enable profile sharing"
                onClick={toggleSharing}
                disabled={busy}
                aria-busy={busy}
              >
                <span />
              </button>
            </div>

            {sharingEnabled && shareUrl && (
              <div className="share-link-section">
                <div className="share-link-fields">
                  <label htmlFor="share-url">Your Shareable Link</label>
                  <div className="share-link-row">
                    <div className="share-url-shell">
                      <span aria-hidden="true">
                        <img src={linkIcon} alt="" />
                      </span>
                      <input id="share-url" readOnly value={shareUrl} />
                    </div>
                    <button className="copy-share-button" type="button" onClick={copyShareLink}>
                      <img src={copyIcon} alt="" />
                      <span>{copied ? "Copied!" : "Copy link"}</span>
                    </button>
                  </div>
                  <p className="share-access-note">
                    <img src={lockIcon} alt="" />
                    <span>Only your shared coding profile is visible. Your account email stays private.</span>
                  </p>
                </div>

                <p className="settings-note">Turning sharing off immediately disables this link.</p>
                <a className="profile-detail-button" href={shareUrl} target="_blank" rel="noopener noreferrer">Preview shared profile ↗</a>
              </div>
            )}
          </section>
    </SettingsLayout>
  );
}

export default SharingPage;
