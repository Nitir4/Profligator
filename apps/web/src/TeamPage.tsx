import { useEffect, useState } from "react";
import { ApiError, AuthUser, getCurrentUser } from "./api";
import userIcon from "./assets/dashboard/user.svg";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

function TeamPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((currentUser) => {
        if (active) setUser(currentUser);
      })
      .catch((requestError: ApiError) => {
        if (requestError.status === 401) {
          window.location.assign("/login");
          return;
        }
        if (active) setError(requestError.message);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="dashboard-page workspace-page">
      <WorkspaceHeader user={user} activeTab="team" />
      <main className="dashboard-main workspace-main">
        <div className="dashboard-content workspace-content">
          <section className="workspace-intro">
            <div>
              <div className="workspace-breadcrumb">
                <a href="/dashboard">Dashboard</a>
                <span aria-hidden="true">/</span>
                <span>Team</span>
              </div>
              <h1>Team</h1>
              <p>Review your workspace and profile sharing options.</p>
            </div>
          </section>

          {error && <p className="dashboard-api-error" role="alert">{error}</p>}

          <section className="workspace-panel" aria-labelledby="team-members-title">
            <div className="workspace-panel-header">
              <div className="workspace-panel-heading">
                <h2 id="team-members-title">Workspace members</h2>
                <span className="workspace-count">1 member</span>
              </div>
            </div>
            <div className="team-member-row">
              <span className="dashboard-avatar" aria-hidden="true">
                <img src={userIcon} alt="" />
              </span>
              <div className="team-member-details">
                <strong>{user?.handle ?? "Candidate"}</strong>
                <span>{user?.email ?? "Loading account…"}</span>
              </div>
              <span className="team-owner-badge">Owner</span>
            </div>
            <p className="workspace-panel-footnote">
              This workspace currently supports one candidate account. Team invitations are not available.
            </p>
          </section>

          <section className="workspace-panel team-sharing-panel" aria-labelledby="team-sharing-title">
            <div className="workspace-panel-header">
              <div className="workspace-panel-heading">
                <h2 id="team-sharing-title">Profile sharing</h2>
              </div>
            </div>
            <div className="team-sharing-row">
              <div>
                <h3>Share your coding profile</h3>
                <p>The sharing controls are a preview. Public share links are not active yet.</p>
              </div>
              <a className="workspace-primary-action" href="/settings/sharing">Open sharing</a>
            </div>
          </section>
        </div>
      </main>
      <WorkspaceFooter />
    </div>
  );
}

export default TeamPage;
