import { useEffect, useState } from "react";
import {
  ApiError,
  AuthUser,
  ConnectorDescriptor,
  getCurrentUser,
  listConnectors,
  listPlatformProfiles,
  PlatformProfile,
  SupportedPlatform,
} from "./api";
import geeksForGeeksIcon from "./assets/profiles/geeksforgeeks.svg";
import leetCodeIcon from "./assets/profiles/leetcode.svg";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

const platforms: {
  key: SupportedPlatform;
  label: string;
  description: string;
  icon?: string;
}[] = [
  {
    key: "codeforces",
    label: "Codeforces",
    description: "Public submissions and solved problems",
  },
  {
    key: "leetcode",
    label: "LeetCode",
    description: "Coding practice preview",
    icon: leetCodeIcon,
  },
  {
    key: "geeksforgeeks",
    label: "GeeksforGeeks",
    description: "Coding practice preview",
    icon: geeksForGeeksIcon,
  },
];

function formatSyncDate(value: string | null) {
  return value
    ? new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : "Not synced yet";
}

function IntegrationsPage() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [connectors, setConnectors] = useState<ConnectorDescriptor[]>([]);
  const [profiles, setProfiles] = useState<PlatformProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then(async (currentUser) => {
        if (!active) return;
        setUser(currentUser);
        const [available, connected] = await Promise.all([listConnectors(), listPlatformProfiles()]);
        if (!active) return;
        setConnectors(available);
        setProfiles(connected);
      })
      .catch((requestError: ApiError) => {
        if (requestError.status === 401) {
          window.location.assign("/login");
          return;
        }
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="dashboard-page workspace-page">
      <WorkspaceHeader user={user} activeTab="integrations" />
      <main className="dashboard-main workspace-main">
        <div className="dashboard-content workspace-content">
          <section className="workspace-intro">
            <div>
              <div className="workspace-breadcrumb">
                <a href="/dashboard">Dashboard</a>
                <span aria-hidden="true">/</span>
                <span>Integrations</span>
              </div>
              <h1>Integrations</h1>
              <p>Connect public coding profiles to bring your activity into one dashboard.</p>
            </div>
            <a className="workspace-primary-action" href="/onboarding/profiles">Manage profiles</a>
          </section>

          {error && <p className="dashboard-api-error" role="alert">{error}</p>}

          <section className="workspace-panel" aria-labelledby="integrations-title">
            <div className="workspace-panel-header">
              <div className="workspace-panel-heading">
                <h2 id="integrations-title">Available platforms</h2>
                <span className="workspace-count">
                  {error ? "—" : loading ? "…" : profiles.length} connected
                </span>
              </div>
              <span className="workspace-panel-caption">Public profiles only</span>
            </div>
            <div className="integration-rows">
              {platforms.map((platform) => {
                const connector = connectors.find((item) => item.platform === platform.key);
                const linked = profiles.filter((profile) => profile.platform === platform.key);
                const live = connector?.live_data ?? platform.key === "codeforces";
                return (
                  <article className="integration-row" key={platform.key}>
                    <span className="integration-platform-mark" aria-hidden="true">
                      {platform.icon ? <img src={platform.icon} alt="" /> : <span>C</span>}
                    </span>
                    <div className="integration-platform-name">
                      <h3>{platform.label}</h3>
                      <span>{platform.description}</span>
                    </div>
                    <span className={`integration-mode ${live ? "live" : "sample"}`}>
                      {live ? "Live API" : "Sample data"}
                    </span>
                    <div className="integration-profiles">
                      {linked.length ? linked.map((profile) => (
                        <div key={profile.id}>
                          <strong>@{profile.public_handle}</strong>
                          <span>Last sync: {formatSyncDate(profile.last_successful_sync)}</span>
                        </div>
                      )) : <span>No profile connected</span>}
                    </div>
                    <a className="integration-row-action" href="/onboarding/profiles">
                      {linked.length ? "Manage" : "Connect"}
                    </a>
                  </article>
                );
              })}
            </div>
            <p className="workspace-panel-footnote">
              LeetCode and GeeksforGeeks use sample data while live collection is evaluated.
              Codeforces uses its public API.
            </p>
          </section>
        </div>
      </main>
      <WorkspaceFooter />
    </div>
  );
}

export default IntegrationsPage;
