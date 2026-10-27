import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getPublicProfile, PublicProfile } from "./api";
import profileLogo from "./assets/profiles/profile-logo.png";
import { ContestHistory, MatchingCoverage, PlatformCoverage, SolvedProblems } from "./ProfileDetails";
import ActivityHeatmap from "./ActivityHeatmap";
import ProfileAvatar from "./ProfileAvatar";

export default function PublicProfilePage({ token }: { token: string }) {
  const [profile, setProfile] = useState<PublicProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const generation = useRef(0);
  const unavailable = useCallback(() => { generation.current++; setProfile(null); setError("This sharing link is unavailable or has been revoked."); }, []);

  useEffect(() => {
    let active = true;
    setProfile(null);
    setError(null);
    const load = () => {
      const current = ++generation.current;
      return getPublicProfile(token).then((value) => {
      if (active && current === generation.current) { setProfile(value); setError(null); }
    }).catch((failure: ApiError) => {
      if (active && current === generation.current) { setProfile(null); setError(failure.status === 404 ? "This sharing link is unavailable or has been revoked."
        : "The shared profile could not be loaded. Try again shortly."); }
    }); };
    void load();
    const focused = () => { if (!document.hidden) void load(); };
    window.addEventListener("focus", focused);
    document.addEventListener("visibilitychange", focused);
    return () => { active = false; window.removeEventListener("focus", focused); document.removeEventListener("visibilitychange", focused); };
  }, [token, retry]);

  const data = profile?.dashboard;
  return (
    <div className="dashboard-page shared-profile-page">
      <header className="setup-header">
        <div className="setup-header-inner">
          <a className="setup-brand" href="/login"><img src={profileLogo} alt="" /><span>Profligator</span></a>
          <span>Shared coding profile</span>
        </div>
      </header>
      <main className="dashboard-main">
        <div className="dashboard-content">
          {error ? <><p role="alert">{error}</p><button className="profile-detail-button" onClick={() => setRetry(value => value + 1)}>Try again</button></> : !data ? <p role="status">Loading profile…</p> : <>
            <section className="sharing-intro">
              <div className="public-profile-identity"><ProfileAvatar profile={profile} className="profile-photo-large" /><div><h1>{profile.display_name || profile.handle}</h1><p>@{profile.handle}</p></div></div>
              {profile.bio && <p className="profile-identity-bio">{profile.bio}</p>}
            </section>
            <section className="profile-detail-card">
              <h2>{data.total_problems_solved} imported problems · {data.unique_problems_solved} unique problems</h2>
              <p>{data.uniqueness_notice}</p>
              {data.unmatched_records > 0 && <p>{data.unmatched_records} records have no confirmed duplicate match.</p>}
              <h3>Topics</h3>
              <ul>{data.topics.items.map((topic) => <li key={topic.name}>{topic.name}: {topic.count}</li>)}</ul>
              <h3>Activity</h3>
              <p>{data.activity.current_streak} day current streak · {data.activity.longest_streak} day longest streak</p>
              <h3>Difficulty</h3>
              <ul>{data.difficulties.items.map((item) => <li key={item.name}>{item.name}: {item.count}</li>)}</ul>
              {data.partial_reasons.map((reason) => <p key={reason}>{reason}</p>)}
            </section>
            <PlatformCoverage dashboard={data} />
            <MatchingCoverage dashboard={data} />
            <ActivityHeatmap dashboard={data} />
            <SolvedProblems shareToken={token} onUnavailable={unavailable} />
            <ContestHistory dashboard={data} />
          </>}
        </div>
      </main>
    </div>
  );
}
