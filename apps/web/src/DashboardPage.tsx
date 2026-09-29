import { useEffect, useMemo, useState } from "react";
import {
  ApiError,
  AuthUser,
  DashboardData,
  getCurrentUser,
  getDashboard,
} from "./api";
import copyLinkIcon from "./assets/dashboard/copy-link.svg";
import shareIcon from "./assets/dashboard/share.svg";
import solvedIcon from "./assets/dashboard/solved.svg";
import verifiedIcon from "./assets/dashboard/verified.svg";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

const heatmapColors = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"];
const difficultyColors: Record<string, string> = {
  Easy: "#10b981",
  Medium: "#f59e0b",
  Hard: "#f43f5e",
};

function addUtcDays(value: Date, days: number) {
  const next = new Date(value);
  next.setUTCDate(next.getUTCDate() + days);
  return next;
}

function utcDateKey(value: Date) {
  return value.toISOString().slice(0, 10);
}

const platformLabels: Record<string, string> = {
  leetcode: "LeetCode",
  geeksforgeeks: "GeeksforGeeks",
  codeforces: "Codeforces",
};

function StatCards({ dashboard, loading }: { dashboard: DashboardData | null; loading: boolean }) {
  const total = dashboard?.total_problems_solved;
  const unique = dashboard?.provisional_unique_problems;
  const uniqueRatio = total && unique !== undefined ? `${((unique / total) * 100).toFixed(1)}%` : "—";

  return (
    <section className="dashboard-stat-grid" aria-label="Problem statistics">
      <article className="dashboard-stat-card total-card" data-node-id="2603:1549">
        <div className="stat-content">
          <div className="stat-label-row">
            <span>Total Problems Solved</span>
            <img src={solvedIcon} alt="" />
          </div>
          <strong className="stat-number">{loading ? "…" : (total ?? 0).toLocaleString()}</strong>
          <p>
            Cumulative problems solved across all {dashboard?.connected_profiles ?? 0} connected
            platforms.
          </p>
        </div>
        <div className="stat-platforms">
          {dashboard?.platforms.length ? (
            dashboard.platforms.map((platform, index) => (
              <span key={`${platform.platform}-${platform.profile_handle}`}>
                {index > 0 && <i aria-hidden="true">•</i>}
                {platformLabels[platform.platform]}: <strong>{platform.solved}</strong>
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
            Deduplicated unique algorithmic problems, excluding identical challenges solved
            across multiple platforms.
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

function ActivityHeatmap({ dashboard }: { dashboard: DashboardData | null }) {
  const [range, setRange] = useState("last-12-months");
  const activity = dashboard?.activity;
  const ranges = useMemo(() => {
    const years = Array.from(
      new Set((activity?.days ?? []).map((day) => day.date.slice(0, 4))),
    ).sort((left, right) => right.localeCompare(left));
    return [
      { key: "last-12-months", label: "Last 12 Months" },
      ...years.slice(0, 3).map((year) => ({ key: year, label: year })),
    ];
  }, [activity]);

  const view = useMemo(() => {
    const counts = new Map((activity?.days ?? []).map((day) => [day.date, day.count]));
    const now = new Date();
    const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const isYear = /^\d{4}$/.test(range);
    const year = isYear ? Number(range) : today.getUTCFullYear();
    const start = isYear
      ? new Date(Date.UTC(year, 0, 1))
      : addUtcDays(today, -364);
    const end = isYear ? new Date(Date.UTC(year, 11, 31)) : today;
    const mondayOffset = (start.getUTCDay() + 6) % 7;
    const gridStart = addUtcDays(start, -mondayOffset);
    const gridEnd = addUtcDays(end, 6 - ((end.getUTCDay() + 6) % 7));
    const maximum = Math.max(
      1,
      ...Array.from(counts.entries())
        .filter(([key]) => key >= utcDateKey(start) && key <= utcDateKey(end))
        .map(([, count]) => count),
    );
    const weeks: Array<Array<{ date: string; count: number; level: number }>> = [];
    for (let weekStart = gridStart; weekStart <= gridEnd; weekStart = addUtcDays(weekStart, 7)) {
      const week = Array.from({ length: 7 }, (_, dayIndex) => {
        const day = addUtcDays(weekStart, dayIndex);
        const key = utcDateKey(day);
        const inRange = day >= start && day <= end;
        const count = inRange ? (counts.get(key) ?? 0) : 0;
        return {
          date: key,
          count,
          level: count === 0 ? 0 : Math.max(1, Math.ceil((count / maximum) * 4)),
        };
      });
      weeks.push(week);
    }
    const monthFormatter = new Intl.DateTimeFormat("en", {
      month: "short",
      timeZone: "UTC",
    });
    const monthStart = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
    const months = Array.from({ length: 12 }, (_, index) =>
      monthFormatter.format(new Date(Date.UTC(monthStart.getUTCFullYear(), monthStart.getUTCMonth() + index, 1))),
    );
    const total = (activity?.days ?? []).reduce(
      (sum, day) =>
        day.date >= utcDateKey(start) && day.date <= utcDateKey(end) ? sum + day.count : sum,
      0,
    );
    return { weeks, months, total };
  }, [activity, range]);

  return (
    <section className="activity-card" aria-labelledby="activity-title" data-node-id="2603:1590">
      <div className="activity-header">
        <div>
          <h2 id="activity-title">Coding Activity</h2>
          <p>{view.total.toLocaleString()} solved records in the selected period</p>
        </div>
        <div className="activity-range" aria-label="Activity period">
          {ranges.map((item) => (
            <button
              className={range === item.key ? "active" : ""}
              key={item.key}
              type="button"
              aria-pressed={range === item.key}
              onClick={() => setRange(item.key)}
            >
              {item.label}
            </button>
          ))}
        </div>
      </div>

      <div
        className="heatmap-scroll"
        role="img"
        aria-label={`${view.total} solved records for ${ranges.find((item) => item.key === range)?.label ?? range}`}
      >
        <div className="heatmap-canvas">
          <div className="month-labels" aria-hidden="true">
            {view.months.map((month, index) => (
              <span key={`${month}-${index}`}>{month}</span>
            ))}
          </div>
          <div className="heatmap-grid-wrap">
            <div className="weekday-labels" aria-hidden="true">
              <span>Mon</span>
              <span>Wed</span>
              <span>Fri</span>
            </div>
            <div
              className="heatmap-grid"
              aria-hidden="true"
              style={{ gridTemplateColumns: `repeat(${view.weeks.length}, 11px)` }}
            >
              {view.weeks.map((week) => (
                <span className="heatmap-week" key={week[0].date}>
                  {week.map((day, dayIndex) => (
                    <i
                      key={day.date}
                      title={`${day.date}: ${day.count}`}
                      style={{
                        top: `${dayIndex * 5.8571429}px`,
                        backgroundColor: heatmapColors[day.level],
                      }}
                    />
                  ))}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="heatmap-footer">
        <div>
          <span>Current streak: <strong>{activity?.current_streak ?? 0} days</strong></span>
          <i aria-hidden="true">•</i>
          <span>Longest streak: <strong>{activity?.longest_streak ?? 0} days</strong></span>
        </div>
        <div className="heatmap-legend" aria-label="Less to more activity">
          <span>Less</span>
          {heatmapColors.map((color) => (
            <i key={color} style={{ backgroundColor: color }} />
          ))}
          <span>More</span>
        </div>
      </div>
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
          <p>Distribution of provider-supplied topic assignments</p>
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
            {dashboard?.difficulties.unrated_records
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
      await navigator.clipboard.writeText("https://profligator.com/p/alex_dev96");
    } catch {
      // The visual confirmation still gives useful feedback in restricted preview contexts.
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
                <h1>{user?.handle ?? "Candidate"}</h1>
                <span>Candidate Profile</span>
              </div>
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
              <span>{dashboard.partial_reasons.join(" ")}</span>
              {dashboard.last_successful_sync && (
                <small>
                  Latest successful sync: {new Date(dashboard.last_successful_sync).toLocaleString()}
                </small>
              )}
            </div>
          )}
          <StatCards dashboard={dashboard} loading={loading} />
          <ActivityHeatmap dashboard={dashboard} />
          <BreakdownCards dashboard={dashboard} />
        </div>
      </main>

      <WorkspaceFooter />
    </div>
  );
}

export default DashboardPage;
