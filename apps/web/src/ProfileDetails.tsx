import { useEffect, useState } from "react";
import { ApiError, DashboardData, getSolvedProblems, SolvedProblemPage } from "./api";

export const platformNames: Record<string, string> = {
  leetcode: "LeetCode", geeksforgeeks: "GeeksforGeeks", codeforces: "Codeforces",
};

export function PlatformCoverage({ dashboard }: { dashboard: DashboardData }) {
  return <section className="profile-detail-card" aria-labelledby="coverage-title">
    <h2 id="coverage-title">Connected platforms</h2>
    <div className="platform-coverage-grid">
      {dashboard.platforms.map((profile) => <article className="platform-coverage" key={`${profile.platform}-${profile.profile_handle}`}>
        <h3>{platformNames[profile.platform]} <span>@{profile.profile_handle}</span></h3>
        <strong>{profile.solved.toLocaleString()} imported</strong>
        <p>{profile.source_total_solved !== null ? `${profile.source_total_solved.toLocaleString()} reported by the platform` : "Platform total unavailable"}</p>
        {profile.source_difficulty_counts && <p>Reported difficulty: {Object.entries(profile.source_difficulty_counts).map(([name, count]) => `${name} ${count}`).join(" · ")}</p>}
        <span className={`coverage-badge ${profile.history_complete ? "complete" : "partial"}`}>
          {profile.history_complete === true ? "Solved count reconciled" : profile.history_complete === false ? "Partial history" : "Coverage unconfirmed"}
        </span>
        {profile.latest_sync_status === "failed" && <p className="profile-fetch-error">Latest sync failed. <a href="/onboarding/profiles">Check this profile's handle</a>.</p>}
        {profile.sync_error && <p className="profile-fetch-error">{profile.sync_error}</p>}
        {profile.platform === "leetcode" && profile.history_complete !== true && <p><a href="/extension/connect">Use the extension to import more available history ↗</a></p>}
        {profile.questions_with_source_times > 0 && <p>{profile.questions_with_source_times} solves have dates in the platform's local clock. View them using the activity source selector.</p>}
        <details className="coverage-details">
        <summary>Sync and coverage details</summary>
        <dl>
          {profile.contests_enabled && <>
            <div><dt>Contest rating</dt><dd>{profile.rating ?? "Unavailable"}</dd></div>
            <div><dt>{profile.platform === "leetcode" ? "Contest rank" : "Rank"}</dt><dd>{profile.rank ?? "Unavailable"}</dd></div>
          </>}
          <div><dt>Profile control</dt><dd>{profile.verification_state === "verified" ? "Verified by source challenge" : profile.verification_state === "fixture_only" ? "Sample profile" : "Not verified"}</dd></div>
          <div><dt>Data source</dt><dd>{profile.connector_mode === "fixture" ? "Sample data" : "Platform data and authorized imports"}</dd></div>
          <div><dt>Question text</dt><dd>{profile.questions_with_statements} / {profile.solved} available</dd></div>
          <div><dt>Known acceptance timestamps</dt><dd>{profile.questions_with_utc_dates} / {profile.solved}</dd></div>
          {profile.questions_with_source_times > 0 && <div><dt>Unzoned source times</dt><dd>{profile.questions_with_source_times}</dd></div>}
          <div><dt>Last successful sync</dt><dd>{profile.last_successful_sync ? new Date(profile.last_successful_sync).toLocaleString() : "Not yet synced"}</dd></div>
          <div><dt>Activity calendar</dt><dd>{profile.activity_years.length ? `Saved years: ${profile.activity_years.join(", ")}` : "Unavailable"}</dd></div>
        </dl>
        {profile.activity_status === "partial" && <p>Activity calendar is partial. Further refreshes can collect remaining public years.</p>}
        {profile.activity_status === "unavailable" && <p>Public calendar could not be refreshed. Previously saved activity is retained.</p>}
        {profile.platform === "leetcode" && <p>Signed-in extension imports can recover more question names and older available Accepted submissions. Timestamps are the earliest observed acceptances; resets or missing history may prevent a first-ever solve date.</p>}
        {profile.platform === "geeksforgeeks" && <p>Source times keep the platform's clock without assuming a time zone. Opening a saved question with the connected extension can recover visible question text.</p>}
        {profile.latest_sync_status && <p>Latest sync: {profile.latest_sync_status}</p>}
        </details>
      </article>)}
      {!dashboard.platforms.length && <p>No connected platforms yet.</p>}
    </div>
  </section>;
}

export function MatchingCoverage({ dashboard }: { dashboard: DashboardData }) {
  return <section className="profile-detail-card" aria-labelledby="matching-title">
    <h2 id="matching-title">Matching coverage</h2>
    <p>{dashboard.records_with_statements} of {dashboard.total_problems_solved} imported questions have text available for comparison.
    </p>
    {dashboard.matching_unavailable_records > 0 && <p role="status">Matching was unavailable for {dashboard.matching_unavailable_records} records. These remain unchecked.</p>}
    <details className="coverage-details">
    <summary>How matching works and its limits</summary>
    <p>{dashboard.semantic_matching === "enabled" ? "Semantic matching is enabled." : "Semantic matching is not enabled. Known question identities and identical statements can still confirm matches."}</p>
    {dashboard.records_without_statements > 0 && <p>{dashboard.records_without_statements} questions have no usable text yet.</p>}
    <p>{dashboard.exact_matched_records} records have confirmed exact matches · {dashboard.semantic_matched_records} have confirmed semantic matches · {dashboard.unmatched_records} have no confirmed duplicate match.</p>
    <p>{dashboard.uniqueness_notice} A question with no confirmed match may still be a duplicate in missing or unchecked history.</p>
    </details>
  </section>;
}

export function ContestHistory({ dashboard }: { dashboard: DashboardData }) {
  const [visible, setVisible] = useState(10);
  if (!dashboard.platforms.some((profile) => profile.contests_enabled && profile.platform !== "geeksforgeeks")) return null;
  return <section className="profile-detail-card" aria-labelledby="contests-title">
    <h2 id="contests-title">Contest history</h2>
    <p>{dashboard.contests.length} imported contests. Ratings and ranks are shown when supplied by the platform.</p>
    {dashboard.contests.length ? <>
      <div className="profile-table-scroll"><table className="profile-table">
        <thead><tr><th>Contest</th><th>Platform</th><th>Date</th><th>Rating</th><th>Contest rank</th></tr></thead>
        <tbody>{dashboard.contests.slice(0, visible).map((contest) => <tr key={`${contest.platform}-${contest.source_id}`}>
          <td><a href={contest.canonical_url} target="_blank" rel="noreferrer">{contest.title}</a></td>
          <td>{platformNames[contest.platform]}</td>
          <td>{contest.occurred_at ? new Date(contest.occurred_at).toLocaleDateString() : "Unavailable"}</td>
          <td>{contest.contest_rating ?? "Unavailable"}</td><td>{contest.global_rank ?? "Unavailable"}</td>
        </tr>)}</tbody>
      </table></div>
      {visible < dashboard.contests.length && <button className="profile-detail-button" type="button" onClick={() => setVisible((value) => value + 20)}>Show more contests</button>}
    </> : <p>No contest history is available from these profiles.</p>}
  </section>;
}

export function SolvedProblems({ shareToken, revision = 0, onUnavailable }: { shareToken?: string; revision?: number; onUnavailable?: () => void }) {
  const [search, setSearch] = useState("");
  const [platform, setPlatform] = useState("");
  const [difficulty, setDifficulty] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<SolvedProblemPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const limit = 10;

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    const timer = window.setTimeout(() => {
      getSolvedProblems({ search, platform, difficulty, offset, limit }, shareToken).then((value) => {
        if (active) setPage(value);
      }).catch((failure: ApiError) => {
        if (active) {
          setPage(null);
          if (shareToken && failure.status === 404) onUnavailable?.();
          setError(shareToken && failure.status === 404 ? "This sharing link is unavailable or has been revoked."
            : "Could not load solved questions. Try again when the service is available.");
        }
      }).finally(() => { if (active) setLoading(false); });
    }, 250);
    return () => { active = false; window.clearTimeout(timer); };
  }, [search, platform, difficulty, offset, shareToken, revision, retry, onUnavailable]);

  return <section className="profile-detail-card" aria-labelledby="solved-title" aria-busy={loading}>
    <h2 id="solved-title">Solved questions</h2>
    <p>Imported questions. Dates appear when available.</p>
    <div className="problem-filters">
      <label>Search questions<input type="search" placeholder="Search by question title" value={search} onChange={(event) => { setSearch(event.target.value); setOffset(0); }} /></label>
      <label>Platform<select value={platform} onChange={(event) => { setPlatform(event.target.value); setOffset(0); }}>
        <option value="">All platforms</option>{Object.entries(platformNames).map(([value, name]) => <option key={value} value={value}>{name}</option>)}
      </select></label>
      <label>Difficulty<select value={difficulty} onChange={(event) => { setDifficulty(event.target.value); setOffset(0); }}>
        <option value="">All difficulties</option>{["School", "Basic", "Easy", "Medium", "Hard"].map((value) => <option key={value}>{value}</option>)}
      </select></label>
    </div>
    {loading ? <p role="status">Loading solved questions…</p> : error ? <div><p role="alert" className="profile-fetch-error">{error}</p><button className="profile-detail-button" onClick={() => setRetry((value) => value + 1)}>Try again</button></div> : page && <>
      <div className="profile-table-scroll"><table className="profile-table">
        <thead><tr><th>Status</th><th>Question</th><th>Platform / account</th><th>Difficulty</th><th>Observed submission date</th></tr></thead>
        <tbody>{page.items.map((problem) => <tr key={problem.id}>
          <td><span className="problem-solved">✓ Solved</span></td>
          <td><a href={problem.canonical_url} target="_blank" rel="noreferrer">{problem.title}</a>
            {problem.topics.length > 0 && <small title={problem.topics.join(", ")}>{problem.topics.slice(0, 3).join(" · ")}</small>}
            {problem.submission_url && <a className="problem-attempt" href={problem.submission_url} target="_blank" rel="noreferrer">View submission ↗</a>}
            <small>{problem.has_statement ? "Question text available" : "Question text unavailable"}</small>
          </td>
          <td>{platformNames[problem.platform]}<small>@{problem.profile_handle}</small></td>
          <td>{problem.difficulty ?? "Unrated"}</td>
          <td>{problem.solved_at ? new Date(problem.solved_at).toLocaleDateString() : problem.source_solved_at ? <>{problem.source_solved_at.replace("T", " ")}<small>Source time · time zone unspecified</small></> : "Unavailable"}</td>
        </tr>)}</tbody>
      </table></div>
      {!page.items.length && <p>No imported questions match these filters.</p>}
      <div className="problem-pagination">
        <span>{page.items.length ? `${offset + 1}–${offset + page.items.length} of ${page.total}` : `0 of ${page.total}`} imported questions</span>
        <div><button className="profile-detail-button" disabled={offset === 0} onClick={() => setOffset((value) => Math.max(0, value - limit))}>Previous</button>
          <button className="profile-detail-button" disabled={offset + limit >= page.total} onClick={() => setOffset((value) => value + limit)}>Next</button></div>
      </div>
    </>}
  </section>;
}
