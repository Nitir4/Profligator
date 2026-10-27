import { useMemo, useState } from "react";
import { DashboardData } from "./api";
import { platformNames } from "./ProfileDetails";

const colors = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"];
const dateKey = (value: Date) => value.toISOString().slice(0, 10);
function addDays(value: Date, days: number) {
  const next = new Date(value); next.setUTCDate(next.getUTCDate() + days); return next;
}

export default function ActivityHeatmap({ dashboard }: { dashboard: DashboardData | null }) {
  const [range, setRange] = useState("last-12-months");
  const [source, setSource] = useState("all");
  const activity = dashboard?.activity;
  const calendars = activity?.source_calendars ?? [];
  const local = calendars.find((item) => `${item.platform}:${item.profile_handle}` === source);
  const combinedDays = useMemo(() => {
    const counts = new Map<string, number>();
    // Source calendars contain only solves without UTC timestamps. Add their
    // reported dates for display without converting them or changing UTC totals.
    for (const series of [activity?.days ?? [], ...calendars.map((item) => item.days)]) {
      for (const day of series) counts.set(day.date, (counts.get(day.date) ?? 0) + day.count);
    }
    return [...counts].sort(([left], [right]) => left.localeCompare(right))
      .map(([date, count]) => ({ date, count }));
  }, [activity?.days, calendars]);
  const combined = source === "all" && calendars.length > 0;
  const days = combined ? combinedDays : local?.days ?? activity?.days ?? [];
  const countLabel = combined ? "activity events" : local ? "dated solves" : activity?.count_label ?? "dated solved records";
  const clockLabel = combined ? "reported dates" : local ? "platform time · timezone unspecified" : "UTC";
  const ranges = useMemo(() => [
    { key: "last-12-months", label: "Last 12 months" },
    ...Array.from(new Set(days.map((day) => day.date.slice(0, 4))))
      .sort((a, b) => b.localeCompare(a)).map((year) => ({ key: year, label: year })),
  ], [days]);

  const view = useMemo(() => {
    const counts = new Map(days.map((day) => [day.date, day.count]));
    const now = new Date();
    const today = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
    const selectedYear = /^\d{4}$/.test(range);
    const year = Number(range);
    const start = selectedYear ? new Date(Date.UTC(year, 0, 1)) : addDays(today, -364);
    const end = selectedYear ? new Date(Date.UTC(year, 11, 31)) : today;
    const gridStart = addDays(start, -((start.getUTCDay() + 6) % 7));
    const gridEnd = addDays(end, 6 - ((end.getUTCDay() + 6) % 7));
    const maximum = Math.max(1, ...days.filter((day) => day.date >= dateKey(start) && day.date <= dateKey(end)).map((day) => day.count));
    const weeks = [];
    const months: { label: string; column: number }[] = [];
    const formatter = new Intl.DateTimeFormat("en", { month: "short", timeZone: "UTC" });
    let lastMonth = "";
    for (let weekStart = gridStart; weekStart <= gridEnd; weekStart = addDays(weekStart, 7)) {
      const week = Array.from({ length: 7 }, (_, index) => {
        const day = addDays(weekStart, index);
        const key = dateKey(day);
        const inRange = day >= start && day <= end;
        const future = day > today;
        const count = counts.get(key) ?? 0;
        if (inRange && key.slice(0, 7) !== lastMonth) {
          months.push({ label: formatter.format(day), column: weeks.length });
          lastMonth = key.slice(0, 7);
        }
        return { date: key, count, inRange, future, level: count === 0 ? 0 : Math.max(1, Math.ceil(count / maximum * 4)) };
      });
      weeks.push(week);
    }
    let longest = 0, run = 0;
    for (let day = start; day <= end && day <= today; day = addDays(day, 1)) {
      run = (counts.get(dateKey(day)) ?? 0) > 0 ? run + 1 : 0;
      longest = Math.max(longest, run);
    }
    let current = 0;
    let day = (counts.get(dateKey(today)) ?? 0) > 0 ? today : addDays(today, -1);
    while (day >= start && day <= end && (counts.get(dateKey(day)) ?? 0) > 0) { current += 1; day = addDays(day, -1); }
    const total = days.filter((item) => item.date >= dateKey(start) && item.date <= dateKey(end)).reduce((sum, item) => sum + item.count, 0);
    const labels = months.filter((month, index) =>
      (months[index + 1]?.column ?? weeks.length) - month.column >= 2);
    return { weeks, months: labels, total, current, longest, width: 32 + weeks.length * 14 };
  }, [days, range]);

  return <section className="activity-card" aria-labelledby="activity-title">
    <div className="activity-header">
      <div><h2 id="activity-title">Coding Activity</h2><p>{view.total.toLocaleString()} {countLabel} in this period · {clockLabel}</p></div>
      <div className="activity-controls">
        {calendars.length > 0 && <select aria-label="Activity source" value={source} onChange={(event) => {
          const value = event.target.value;
          setSource(value);
          const selected = calendars.find((item) => `${item.platform}:${item.profile_handle}` === value);
          setRange(selected?.days.at(-1)?.date.slice(0, 4) ?? "last-12-months");
        }}>
          <option value="all">All activity</option>
          <option value="utc">UTC activity</option>
          {calendars.map((item) => <option key={`${item.platform}:${item.profile_handle}`} value={`${item.platform}:${item.profile_handle}`}>{platformNames[item.platform]} @{item.profile_handle} · source dates</option>)}
        </select>}
        <select aria-label="Activity period" value={range} onChange={(event) => setRange(event.target.value)}>
          {ranges.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}
        </select>
      </div>
    </div>
    <div className="heatmap-scroll" tabIndex={0} aria-label="Scrollable activity calendar">
      <div className="heatmap-canvas">
        <svg viewBox={`0 0 ${view.width} 130`} role="img" aria-label={`${view.total} ${countLabel} · ${clockLabel}`}>
          {view.months.map((month, index) => <text key={index} x={32 + month.column * 14} y={13} className="heatmap-label">{month.label}</text>)}
          {[{ name: "Mon", row: 0 }, { name: "Wed", row: 2 }, { name: "Fri", row: 4 }].map((day) => <text key={day.name} x={0} y={35 + day.row * 14} className="heatmap-weekday">{day.name}</text>)}
          {view.weeks.map((week, column) => week.map((day, row) => <rect key={day.date} data-date={day.date} data-count={day.count}
            x={32 + column * 14} y={26 + row * 14} width={11} height={11} rx={2}
            fill={colors[day.level]} opacity={!day.inRange ? 0 : day.future ? 0.3 : 1}>
            <title>{day.future ? `${day.date}: future date` : `${day.date}: ${day.count} ${countLabel} · ${clockLabel}`}</title>
          </rect>))}
        </svg>
      </div>
    </div>
    <p className="activity-scroll-hint">Scroll to see the full year.</p>
    <div className="heatmap-footer"><div><span>Current streak: <strong>{view.current} days</strong></span><span>Longest in period: <strong>{view.longest} days</strong></span></div>
      <div className="heatmap-legend" aria-label="Less to more activity"><span>Less</span>{colors.map((color) => <i key={color} style={{ backgroundColor: color }} />)}<span>More</span></div>
    </div>
    <details className="coverage-details"><summary>Activity sources and missing dates</summary>
      <p>{combined ? "All activity includes UTC submissions and dated solves, plus platform-local solves such as GeeksforGeeks. Dates and streaks use each source's reported calendar date; unknown timezones are not converted to UTC. Activity events are not a count of unique solved questions." : local ? "These solved-question dates use the platform's clock. Its timezone is unknown." : "UTC activity combines saved public submission calendars with dated solves where a calendar is unavailable. It is not a count of unique solved questions."}</p>
      <ul className="activity-coverage">{dashboard?.platforms.map((profile) => <li key={`${profile.platform}:${profile.profile_handle}`}>
        <strong>{platformNames[profile.platform]}</strong>: {profile.latest_sync_status === "failed" ? "Latest sync failed; showing any saved activity." : profile.activity_years.length ? `Saved calendar years: ${profile.activity_years.join(", ")}.` : profile.questions_with_utc_dates ? `${profile.questions_with_utc_dates} solves have UTC dates.` : "No UTC activity dates available."}
        {profile.questions_with_source_times > 0 && ` ${profile.questions_with_source_times} solves have platform-local dates; choose their source above.`}
      </li>)}</ul>
      {(activity?.unknown_timestamp_records ?? 0) > 0 && <p>{activity?.unknown_timestamp_records} imported questions lack a UTC timestamp. Unavailable dates are not treated as proof of inactivity.</p>}
    </details>
  </section>;
}
