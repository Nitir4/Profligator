import { FormEvent, useEffect, useState } from "react";
import { ApiError, AuthUser, getCurrentUser } from "./api";
import userIcon from "./assets/dashboard/user.svg";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

function TeamPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profileLink, setProfileLink] = useState("");
  const [linkError, setLinkError] = useState<string | null>(null);

  function openProfile(event: FormEvent) {
    event.preventDefault();
    setLinkError(null);
    try {
      const url = new URL(profileLink.trim(), window.location.origin);
      if (url.origin !== window.location.origin || !/^\/p\/[A-Za-z0-9_-]{16,128}\/?$/.test(url.pathname)) throw new Error();
      window.location.assign(url.pathname.replace(/\/$/, ""));
    } catch { setLinkError("Enter a shared Profligator profile link from this site."); }
  }

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
                <a href={user?.role === "recruiter" ? "/team" : "/dashboard"}>Workspace</a>
                <span aria-hidden="true">/</span>
                <span>{user?.role === "recruiter" ? "Shared profiles" : "Team"}</span>
              </div>
              <h1>{user?.role === "recruiter" ? "Shared profiles" : "Team"}</h1>
              <p>{user?.role === "recruiter" ? "Review coding profiles that candidates have chosen to share with you." : "Review your workspace and profile sharing options."}</p>
            </div>
          </section>

          {error && <p className="dashboard-api-error" role="alert">{error}</p>}

          {user?.role === "recruiter" && <section className="workspace-panel profile-detail-card">
            <h2>Open a candidate profile</h2>
            <p>Ask the candidate for their sharing link. It opens their imported questions, activity and coverage.</p>
            <form onSubmit={openProfile} className="problem-filters">
              <label>Shared profile link<input type="text" required value={profileLink} placeholder={`${window.location.origin}/p/…`}
                onChange={event => setProfileLink(event.target.value)} /></label>
              <button className="profile-detail-button" type="submit">Open profile</button>
            </form>
            {linkError && <p className="profile-fetch-error" role="alert">{linkError}</p>}
            <p>Access ends when the candidate disables sharing. Missing history and unchecked questions are labeled in each profile.</p>
          </section>}

          {user?.role === "candidate" && <><section className="workspace-panel" aria-labelledby="team-members-title">
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
                <p>Enable sharing to create a public profile link. You can disable sharing to revoke it at any time.</p>
              </div>
              <a className="workspace-primary-action" href="/settings/sharing">Open sharing</a>
            </div>
          </section></>}
        </div>
      </main>
      <WorkspaceFooter />
    </div>
  );
}

export default TeamPage;
