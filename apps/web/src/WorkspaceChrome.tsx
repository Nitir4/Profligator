import { useEffect, useRef, useState } from "react";
import { AuthUser, logoutCandidate } from "./api";
import brandMarkIcon from "./assets/dashboard/brand-mark.svg";
import chevronDownIcon from "./assets/dashboard/chevron-down.svg";
import ProfileAvatar from "./ProfileAvatar";

type WorkspaceTab = "dashboard" | "profiles" | "integrations" | "team" | "account";

const tabs: { key: WorkspaceTab; label: string; href: string }[] = [
  { key: "dashboard", label: "Dashboard", href: "/dashboard" },
  { key: "profiles", label: "Profiles", href: "/onboarding/profiles" },
  { key: "integrations", label: "Integrations", href: "/integrations" },
  { key: "team", label: "Team", href: "/team" },
];

export function WorkspaceHeader({ user, activeTab }: { user: AuthUser | null; activeTab: WorkspaceTab }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menuOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const closeEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setMenuOpen(false); menuRef.current?.querySelector("button")?.focus(); }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeEscape);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", closeEscape); };
  }, [menuOpen]);

  async function signOut() {
    await logoutCandidate().catch(() => undefined);
    window.location.assign("/login");
  }

  return (
    <header className="dashboard-header">
      <div className="dashboard-header-inner">
        <div className="dashboard-nav-group">
          <a className="dashboard-brand" href={user?.role === "recruiter" ? "/team" : "/dashboard"} aria-label="Profligator home">
            <span className="dashboard-brand-mark" aria-hidden="true">
              <img src={brandMarkIcon} alt="" />
            </span>
            <span>Profligator</span>
          </a>
          <span className="dashboard-nav-divider" aria-hidden="true" />
          <nav className="dashboard-primary-nav" aria-label="Primary navigation">
            {tabs.filter(tab => user?.role !== "recruiter" || tab.key === "team").map((tab) => (
              <a
                key={tab.key}
                className={activeTab === tab.key ? "active" : undefined}
                href={tab.href}
                aria-current={activeTab === tab.key ? "page" : undefined}
              >
                {tab.key === "team" && user?.role === "recruiter" ? "Shared profiles" : tab.label}
              </a>
            ))}
          </nav>
        </div>

        <div className="dashboard-account-area">
          <a href="/documentation">Documentation</a>
          <span className="dashboard-nav-divider" aria-hidden="true" />
          <div className="dashboard-user-wrap" ref={menuRef}>
            <button
              className="dashboard-user-menu-button dashboard-account-trigger"
              type="button"
              aria-label="Open user menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
            <ProfileAvatar profile={user} className="dashboard-avatar" />
            <span className="dashboard-user-copy">
              <strong>{user?.display_name || user?.handle || "Candidate"}</strong>
              <span>{user?.email ?? "Loading…"}</span>
            </span>
              <img className="account-chevron" src={chevronDownIcon} alt="" />
            </button>
            {menuOpen && (
              <div className="dashboard-user-menu">
                <a href="/settings/account#profile">Edit profile</a>
                <a href="/settings/account">Account settings</a>
                {user?.role === "candidate" && <><a href="/onboarding/profiles">Manage profiles</a>
                <a href="/settings/sharing">Sharing settings</a></>}
                <button type="button" onClick={signOut}>Sign out</button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

export function WorkspaceFooter() {
  return (
    <footer className="dashboard-footer">
      <div className="dashboard-footer-inner">
        <p>© 2026 Profligator Inc. All rights reserved.</p>
        <nav aria-label="Legal and support links">
          <a href="/privacy">Privacy</a>
          <a href="/terms">Terms</a>
          <a href="/status">Status</a>
          <a href="/support">Contact Support</a>
        </nav>
      </div>
    </footer>
  );
}
