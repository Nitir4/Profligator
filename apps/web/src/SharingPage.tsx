import { useState } from "react";
import documentationIcon from "./assets/profiles/documentation.svg";
import profileLogo from "./assets/profiles/profile-logo.png";
import copyIcon from "./assets/sharing/copy.svg";
import infoIcon from "./assets/sharing/info.svg";
import linkIcon from "./assets/sharing/link.svg";
import lockIcon from "./assets/sharing/lock.svg";

const shareUrl = "https://profligator.com/p/alex_dev96";

function SharingPage() {
  const [sharingEnabled, setSharingEnabled] = useState(true);
  const [copied, setCopied] = useState(false);

  async function copyShareLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
    } catch {
      // Clipboard access can be unavailable in local or restricted preview contexts.
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="sharing-page" data-node-id="2603:2226">
      <header className="setup-header" data-node-id="2603:2292">
        <div className="setup-header-inner">
          <a className="setup-brand" href="/dashboard" aria-label="Profligator dashboard">
            <img src={profileLogo} alt="" />
            <span>Profligator</span>
          </a>

          <div className="setup-header-actions">
            <a className="setup-docs-link" href="#documentation">
              <img src={documentationIcon} alt="" />
              <span>Documentation</span>
            </a>
            <span className="header-divider" aria-hidden="true" />
            <div className="account-chip">
              <span className="account-avatar" aria-hidden="true">
                AD
              </span>
              <span>alex@example.com</span>
            </div>
          </div>
        </div>
      </header>

      <main className="sharing-main">
        <div className="sharing-content">
          <section className="sharing-intro" aria-labelledby="sharing-title">
            <div className="sharing-breadcrumb" aria-label="Breadcrumb">
              <a href="/dashboard">Dashboard</a>
              <span aria-hidden="true">/</span>
              <span>Profile Sharing</span>
            </div>
            <h1 id="sharing-title">Profile Sharing</h1>
            <p>Share your Profligator profile with others using a secure link.</p>
          </section>

          <section className="sharing-card" data-node-id="2603:2241">
            <div className="sharing-toggle-row">
              <div>
                <h2>Profile Sharing</h2>
                <p>When sharing is enabled, people with the link can view your profile.</p>
              </div>
              <button
                className={`sharing-switch${sharingEnabled ? " enabled" : ""}`}
                type="button"
                role="switch"
                aria-checked={sharingEnabled}
                aria-label="Enable profile sharing"
                onClick={() => setSharingEnabled((enabled) => !enabled)}
              >
                <span />
              </button>
            </div>

            {sharingEnabled && (
              <div className="share-link-section" data-node-id="2603:2252">
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
                    <span>Anyone with this link can view your Unified Coding Statistics.</span>
                  </p>
                </div>

                <div className="sharing-callout">
                  <img src={infoIcon} alt="" />
                  <p>
                    You can turn off sharing at any time. When disabled, existing links will
                    immediately show an
                    <br />
                    unavailable page.
                  </p>
                </div>
              </div>
            )}
          </section>
        </div>
      </main>

      <footer className="setup-footer" data-node-id="2603:2279">
        <div className="setup-footer-inner">
          <p>© 2026 Profligator Inc. All rights reserved.</p>
          <nav aria-label="Legal and support links">
            <a href="#privacy">Privacy</a>
            <a href="#terms">Terms</a>
            <a href="#status">Status</a>
            <a href="#support">Contact Support</a>
          </nav>
        </div>
      </footer>
    </div>
  );
}

export default SharingPage;
