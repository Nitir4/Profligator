import { useState } from "react";
import brandMarkIcon from "./assets/dashboard/brand-mark.svg";
import chevronDownIcon from "./assets/dashboard/chevron-down.svg";
import copyLinkIcon from "./assets/dashboard/copy-link.svg";
import shareIcon from "./assets/dashboard/share.svg";
import solvedIcon from "./assets/dashboard/solved.svg";
import userIcon from "./assets/dashboard/user.svg";
import verifiedIcon from "./assets/dashboard/verified.svg";

const heatmapWeeks = [
  "0120130",
  "1234201",
  "2301220",
  "0134210",
  "1023301",
  "3242100",
  "0120321",
  "2334201",
  "1201340",
  "0012231",
  "1230120",
  "3421013",
  "0123240",
  "1012301",
  "2301420",
  "0123103",
  "1234210",
  "0123012",
  "2342100",
  "1230123",
  "0124210",
  "1230120",
  "3242101",
  "0123012",
  "1234210",
  "0102321",
  "2342100",
  "1230123",
  "0124210",
  "1230120",
  "3242101",
  "0123012",
  "1234210",
  "0102321",
  "2342100",
  "1230123",
];

const heatmapColors = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"];

const topics = [
  { name: "Arrays & Hashing", count: 248, percent: 27.7 },
  { name: "Dynamic Programming", count: 184, percent: 20.6 },
  { name: "Trees & Binary Search", count: 146, percent: 16.3 },
  { name: "Graphs & BFS/DFS", count: 122, percent: 13.6 },
  { name: "Strings & Two Pointers", count: 108, percent: 12.1 },
  { name: "Math & Bit Manipulation", count: 86, percent: 9.6 },
];

const difficulties = [
  { name: "Easy", count: 312, percent: 34.9, color: "#10b981" },
  { name: "Medium", count: 476, percent: 53.2, color: "#f59e0b" },
  { name: "Hard", count: 106, percent: 11.9, color: "#f43f5e" },
];

function DashboardHeader() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="dashboard-header" data-node-id="2603:2024">
      <div className="dashboard-header-inner">
        <div className="dashboard-nav-group">
          <a className="dashboard-brand" href="/dashboard" aria-label="Profligator dashboard">
            <span className="dashboard-brand-mark" aria-hidden="true">
              <img src={brandMarkIcon} alt="" />
            </span>
            <span>Profligator</span>
          </a>
          <span className="dashboard-nav-divider" aria-hidden="true" />
          <nav className="dashboard-primary-nav" aria-label="Primary navigation">
            <a className="active" href="/dashboard" aria-current="page">
              Dashboard
            </a>
            <a href="/onboarding/profiles">Profiles</a>
            <a href="#integrations">Integrations</a>
            <a href="#team">Team</a>
          </nav>
        </div>

        <div className="dashboard-account-area">
          <a href="#documentation">Documentation</a>
          <span className="dashboard-nav-divider" aria-hidden="true" />
          <div className="dashboard-user-wrap">
            <span className="dashboard-avatar" aria-hidden="true">
              <img src={userIcon} alt="" />
            </span>
            <span className="dashboard-user-copy">
              <strong>Alex</strong>
              <span>alex@example.com</span>
            </span>
            <button
              className="dashboard-user-menu-button"
              type="button"
              aria-label="Open user menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <img src={chevronDownIcon} alt="" />
            </button>
            {menuOpen && (
              <div className="dashboard-user-menu">
                <a href="/onboarding/profiles">Manage profiles</a>
                <a href="/login">Sign out</a>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function StatCards() {
  return (
    <section className="dashboard-stat-grid" aria-label="Problem statistics">
      <article className="dashboard-stat-card total-card" data-node-id="2603:1549">
        <div className="stat-content">
          <div className="stat-label-row">
            <span>Total Problems Solved</span>
            <img src={solvedIcon} alt="" />
          </div>
          <strong className="stat-number">1,428</strong>
          <p>Cumulative problems solved across all 3 connected platforms.</p>
        </div>
        <div className="stat-platforms">
          <span>LeetCode: <strong>812</strong></span>
          <i aria-hidden="true">•</i>
          <span>Codeforces: <strong>386</strong></span>
          <i aria-hidden="true">•</i>
          <span>HackerRank: <strong>230</strong></span>
        </div>
      </article>

      <article className="dashboard-stat-card unique-card" data-node-id="2603:1572">
        <div className="stat-content">
          <div className="stat-label-row">
            <span>Unique Problems Solved</span>
            <span className="unique-ratio">62.6% unique ratio</span>
          </div>
          <strong className="stat-number">894</strong>
          <p>
            Deduplicated unique algorithmic problems, excluding identical challenges solved
            across multiple platforms.
          </p>
        </div>
        <div className="normalized-note">
          <img src={verifiedIcon} alt="" />
          <span>Normalized across algorithmic classification standards</span>
        </div>
      </article>
    </section>
  );
}

function ActivityHeatmap() {
  const [range, setRange] = useState("Last 12 Months");
  const ranges = ["Last 12 Months", "2024", "2023"];

  return (
    <section className="activity-card" aria-labelledby="activity-title" data-node-id="2603:1590">
      <div className="activity-header">
        <div>
          <h2 id="activity-title">Coding Activity</h2>
          <p>642 submissions in the past year</p>
        </div>
        <div className="activity-range" aria-label="Activity period">
          {ranges.map((item) => (
            <button
              className={range === item ? "active" : ""}
              key={item}
              type="button"
              aria-pressed={range === item}
              onClick={() => setRange(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="heatmap-scroll" role="img" aria-label={`Submission activity for ${range}`}>
        <div className="heatmap-canvas">
          <div className="month-labels" aria-hidden="true">
            {[
              "Jan",
              "Feb",
              "Mar",
              "Apr",
              "May",
              "Jun",
              "Jul",
              "Aug",
              "Sep",
              "Oct",
              "Nov",
              "Dec",
            ].map((month) => (
              <span key={month}>{month}</span>
            ))}
          </div>
          <div className="heatmap-grid-wrap">
            <div className="weekday-labels" aria-hidden="true">
              <span>Mon</span>
              <span>Wed</span>
              <span>Fri</span>
            </div>
            <div className="heatmap-grid" aria-hidden="true">
              {heatmapWeeks.map((week, weekIndex) => (
                <span className="heatmap-week" key={`${week}-${weekIndex}`}>
                  {[...week].map((level, dayIndex) => (
                    <i
                      key={`${weekIndex}-${dayIndex}`}
                      style={{
                        top: `${dayIndex * 5.8571429}px`,
                        backgroundColor: heatmapColors[Number(level)],
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
          <span>Current streak: <strong>14 days</strong></span>
          <i aria-hidden="true">•</i>
          <span>Longest streak: <strong>42 days</strong></span>
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

function BreakdownCards() {
  return (
    <section className="dashboard-breakdowns">
      <article className="breakdown-card topic-card" data-node-id="2603:1912">
        <div className="breakdown-heading">
          <h2>Topic Breakdown</h2>
          <p>Distribution of solved problems by category</p>
        </div>
        <div className="topic-list">
          {topics.map((topic) => (
            <div className="topic-row" key={topic.name}>
              <div>
                <span>{topic.name}</span>
                <span className="topic-value">
                  {topic.count} solved <i aria-hidden="true">·</i> {topic.percent}%
                </span>
              </div>
              <span className="topic-track">
                <i style={{ width: `${topic.percent}%` }} />
              </span>
            </div>
          ))}
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
          <span>Combined algorithmic problems</span>
          <strong>894 Total</strong>
        </div>
      </article>
    </section>
  );
}

function DashboardPage() {
  const [copied, setCopied] = useState(false);

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
      <DashboardHeader />

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
                <h1>Alex</h1>
                <span>Senior Software Engineer</span>
              </div>
              <div className="connected-pills" aria-label="Connected profiles">
                {[
                  ["LeetCode", "alex_dev"],
                  ["GitHub", "alex-dev"],
                  ["Codeforces", "alex_cf"],
                ].map(([platform, handle]) => (
                  <span className="connected-pill" key={platform}>
                    <i aria-hidden="true" />
                    <strong>{platform}:</strong>
                    <span>{handle}</span>
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

          <StatCards />
          <ActivityHeatmap />
          <BreakdownCards />
        </div>
      </main>

      <footer className="dashboard-footer" data-node-id="2603:2011">
        <div className="dashboard-footer-inner">
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

export default DashboardPage;
