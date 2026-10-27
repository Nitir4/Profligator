import { ReactNode } from "react";
import { AuthUser } from "./api";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

export default function SettingsLayout({ user, active, title, description, children }: {
  user: AuthUser | null; active: "account" | "sharing"; title: string; description: string; children: ReactNode;
}) {
  return <div className="dashboard-page settings-page">
    <WorkspaceHeader user={user} activeTab="account" />
    <main className="settings-main">
      <aside className="settings-sidebar">
        <span className="settings-eyebrow">Settings</span>
        <nav aria-label="Settings navigation">
          <a href="/settings/account" aria-current={active === "account" ? "page" : undefined}>Account & sign-in</a>
          {user?.role !== "recruiter" && <a href="/settings/sharing" aria-current={active === "sharing" ? "page" : undefined}>Profile sharing</a>}
          {user?.role !== "recruiter" && <a href="/extension/connect">Browser extension</a>}
        </nav>
        <a className="settings-back" href={user?.role === "recruiter" ? "/team" : "/dashboard"}>← Back to workspace</a>
      </aside>
      <div className="settings-content">
        <header className="settings-heading"><h1>{title}</h1><p>{description}</p></header>
        {children}
      </div>
    </main>
    <WorkspaceFooter />
  </div>;
}
