import { useEffect, useState } from "react";
import {
  ApiError,
  AuthUser,
  DashboardData,
  getCurrentUser,
  getDashboard,
  getSharing,
  listPlatformProfiles,
  startProfileSync,
  waitForSync,
} from "./api";
import { ContestHistory, MatchingCoverage, PlatformCoverage, SolvedProblems } from "./ProfileDetails";
import ActivityHeatmap from "./ActivityHeatmap";
import copyLinkIcon from "./assets/dashboard/copy-link.svg";
import shareIcon from "./assets/dashboard/share.svg";
import solvedIcon from "./assets/dashboard/solved.svg";
import verifiedIcon from "./assets/dashboard/verified.svg";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";
import ProfileAvatar from "./ProfileAvatar";

const difficultyColors: Record<string, string> = {
  Fundamentals: "#6366f1",
  Easy: "#10b981",
  Medium: "#f59e0b",
  Hard: "#f43f5e",
};

const platformLabels: Record<string, string> = {
  leetcode: "LeetCode",
  geeksforgeeks: "GeeksforGeeks",
  codeforces: "Codeforces",
};

function StatCards({ dashboard, loading }: { dashboard: DashboardData | null; loading: boolean }) {
  const total = dashboard?.total_problems_solved;
  const unique = dashboard?.unique_problems_solved;
  const uniqueRatio = total && unique !== undefined ? `${((unique / total) * 100).toFixed(1)}%` : "—";

  return (
    <section className="dashboard-stat-grid" aria-label="Problem statistics">
      <article className="dashboard-stat-card total-card" data-node-id="2603:1549">
        <div className="stat-content">
          <div className="stat-label-row">
            <span>Imported Solved Problems</span>
            <img src={solvedIcon} alt="" />
          </div>
          <strong className="stat-number">{loading ? "…" : (total ?? 0).toLocaleString()}</strong>
          <p>
            Imported from {dashboard?.connected_profiles ?? 0} connected
            {dashboard?.connected_profiles === 1 ? " profile" : " profiles"}.
          </p>
        </div>
        <div className="stat-platforms">
          {dashboard?.platforms.length ? (
            dashboard.platforms.map((platform, index) => (
              <span key={`${platform.platform}-${platform.profile_handle}`}>
                {index > 0 && <i aria-hidden="true">•</i>}
                {platformLabels[platform.platform]}: <strong>{platform.solved}</strong>
                {platform.source_total_solved !== null && ` / ${platform.source_total_solved} reported`}
              </span>
            ))
          ) : (
            <span>No synchronized profiles yet</span>
          )}
        </div>
      </article>

      <article className="dashboard-stat-card unique-card" data-node-id="2603:1572">
        <div className="stat-content">
          <div className="stat-label-row">
            <span>Unique Problems Solved</span>
            <span className="unique-ratio">{uniqueRatio} unique ratio</span>
          </div>
          <strong className="stat-number">{loading ? "…" : (unique ?? 0).toLocaleString()}</strong>
          <p>
            Imported problems after confirmed duplicates are removed.
          </p>
        </div>
        <div className="normalized-note">
          <img src={verifiedIcon} alt="" />
          <span>{dashboard?.uniqueness_notice ?? "Waiting for synchronized profile data"}</span>
        </div>
      </article>
    </section>
  );
}


function BreakdownCards({ dashboard }: { dashboard: DashboardData | null }) {
  const topics = dashboard?.topics.items ?? [];
  const difficulties = (dashboard?.difficulties.items ?? []).map((difficulty) => ({
    ...difficulty,
    color: difficultyColors[difficulty.name] ?? "#94a3b8",
  }));

  return (
    <section className="dashboard-breakdowns">
      <article className="breakdown-card topic-card" data-node-id="2603:1912">
        <div className="breakdown-heading">
          <h2>Topic Breakdown</h2>
          <p>Topics in your imported history</p>
        </div>
        <div className="topic-list">
          {topics.length ? (
            topics.map((topic) => (
              <div className="topic-row" key={topic.name}>
                <div>
                  <span>{topic.name}</span>
                  <span className="topic-value">
                    {topic.count} tagged <i aria-hidden="true">·</i> {topic.percent}%
                  </span>
                </div>
                <span className="topic-track">
                  <i style={{ width: `${topic.percent}%` }} />
                </span>
              </div>
            ))
          ) : (
            <p className="dashboard-empty-copy">No topic metadata is available yet.</p>
          )}
        </div>
      </article>

      <article className="breakdown-card difficulty-card" data-node-id="2603:1968">
        <div className="breakdown-heading">
          <h2>Difficulty Breakdown</h2>
          <p>Distribution by challenge difficulty</p>
        </div>
        <div className="difficulty-bar" aria-label="Difficulty distribution">
          {difficulties.map((difficulty) => (
            <i
              key={difficulty.name}
              style={{
                width: `${difficulty.percent}%`,
                backgroundColor: difficulty.color,
              }}
            />
          ))}
        </div>
        <div className="difficulty-list">
          {difficulties.map((difficulty) => (
            <div className="difficulty-row" key={difficulty.name}>
              <span className="difficulty-name">
                <i style={{ backgroundColor: difficulty.color }} />
                {difficulty.name}
              </span>
              <span>
                <strong>{difficulty.count}</strong>
                <small>{difficulty.percent}%</small>
              </span>
            </div>
          ))}
        </div>
        <div className="difficulty-summary">
          <span>
            {!dashboard?.total_problems_solved
              ? "No rated questions yet"
              : dashboard.difficulties.unrated_records
              ? `${dashboard.difficulties.unrated_records} unrated records excluded`
              : "All synchronized records are rated"}
          </span>
          <strong>{dashboard?.difficulties.rated_records ?? 0} Rated</strong>
        </div>
      </article>
    </section>
  );
}

function DashboardPage() {
  const [copied, setCopied] = useState(false);
  const [dashboard, setDashboard] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((currentUser) => {
        if (!active) return null;
        setUser(currentUser);
        return getDashboard();
      })
      .then((data) => {
        if (data === null) return;
        if (!active) return;
        setDashboard(data);
        setError(null);
        // Show saved data immediately, then refresh the owner's accounts.
        // The API reuses current jobs and enforces the per-profile cooldown.
        void listPlatformProfiles().then(async (profiles) => {
          if (!active || !profiles.length) return;
          setSyncMessage("Checking connected profiles for updates…");
          const results = [];
          for (const profile of profiles) {
            if (!active) return;
            try {
              await waitForSync(await startProfileSync(profile.id));
              results.push(true);
            } catch {
              results.push(false);
            }
          }
          if (!active) return;
          const latest = await getDashboard();
          if (!active) return;
          setDashboard(latest);
          setRevision((value) => value + 1);
          setSyncMessage(results.every(Boolean) ? "Profile check complete. Recently synced profiles use saved data." : "Some profiles could not refresh. Showing their last saved data.");
        }).catch(() => {
          if (active) setSyncMessage("Could not check for updates. Showing saved profile data.");
        });
      })
      .catch((requestError: ApiError) => {
        if (requestError.status === 401) {
          window.location.assign("/login");
          return;
        }
        if (active) setError(requestError.message);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  async function copyProfileLink() {
    try {
      const sharing = await getSharing();
      if (!sharing.enabled || !sharing.shareable_link) {
        window.location.assign("/settings/sharing");
        return;
      }
      await navigator.clipboard.writeText(sharing.shareable_link);
    } catch {
      setError("Could not copy the profile link.");
      return;
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="dashboard-page" data-node-id="2603:1500">
      <WorkspaceHeader user={user} activeTab="dashboard" />

      <main className="dashboard-main">
        <div className="dashboard-content">
          <section className="dashboard-profile-header" data-node-id="2603:1504">
            <div className="dashboard-profile-copy">
              <div className="dashboard-breadcrumb">
                <span>Dashboard</span>
                <span aria-hidden="true">/</span>
                <span>Overview</span>
              </div>
              <div className="dashboard-name-row">
                <ProfileAvatar profile={user} className="dashboard-profile-photo" />
                <h1>{user?.display_name || user?.handle || "Candidate"}</h1>
                <span>Candidate Profile</span>
              </div>
              {user?.display_name && <p className="profile-identity-handle">@{user.handle}</p>}
              {user?.bio && <p className="profile-identity-bio">{user.bio}</p>}
              <div className="connected-pills" aria-label="Connected profiles">
                {dashboard?.platforms.map((profile) => (
                  <span
                    className="connected-pill"
                    key={`${profile.platform}-${profile.profile_handle}`}
                  >
                    <i aria-hidden="true" />
                    <strong>{platformLabels[profile.platform]}:</strong>
                    <span>{profile.profile_handle}</span>
                  </span>
                ))}
              </div>
            </div>

            <div className="dashboard-profile-actions">
              <button type="button" onClick={copyProfileLink}>
                <img src={copyLinkIcon} alt="" />
                <span>{copied ? "Copied!" : "Copy Link"}</span>
              </button>
              <a className="share-profile-button" href="/settings/sharing">
                <img src={shareIcon} alt="" />
                <span>Share Profile</span>
              </a>
            </div>
          </section>

          {error && (
            <p className="dashboard-api-error" role="alert">
              {error}
            </p>
          )}
          {dashboard?.data_state === "empty" && (
            <div className="dashboard-data-notice empty" role="status">
              <strong>No synchronized problem data yet.</strong>
              <span>Connect a supported profile and run its first sync to populate analytics.</span>
              <a href="/onboarding/profiles">Manage profiles</a>
            </div>
          )}
          {dashboard?.data_state === "partial" && (
            <div className="dashboard-data-notice" role="status">
              <strong>Some analytics are incomplete.</strong>
              <span>See the status and next steps for each connected platform below.</span>
              <a href="#coverage-title">View affected profiles</a>
            </div>
          )}
          <StatCards dashboard={dashboard} loading={loading} />
          {syncMessage && <p className="profile-sync-message" role="status">{syncMessage}</p>}
          {dashboard && <PlatformCoverage dashboard={dashboard} />}
          {dashboard && <MatchingCoverage dashboard={dashboard} />}
          <ActivityHeatmap dashboard={dashboard} />
          <BreakdownCards dashboard={dashboard} />
          {dashboard && <ContestHistory dashboard={dashboard} />}
          {dashboard && <SolvedProblems revision={revision} />}
        </div>
      </main>

      <WorkspaceFooter />
    </div>
  );
}

export default DashboardPage;
