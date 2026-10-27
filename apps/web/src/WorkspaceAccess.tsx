import { ReactNode, useEffect, useState } from "react";
import { ApiError, AuthUser, getCurrentUser } from "./api";

export default function WorkspaceAccess({ role, children }: { role?: AuthUser["role"]; children: ReactNode }) {
  const [allowed, setAllowed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setAllowed(false);
    setError(null);
    getCurrentUser().then(user => {
      if (!active) return;
      if (role && user.role !== role) {
        window.location.replace(user.role === "recruiter" ? "/team" : "/dashboard");
        return;
      }
      setAllowed(true);
    }).catch((failure: ApiError) => {
      if (!active) return;
      if (failure.status === 401) window.location.replace("/login");
      else setError(failure.message);
    });
    return () => { active = false; };
  }, [role, retry]);
  if (allowed) return children;
  return <main className="dashboard-main"><div className="dashboard-content">
    {error ? <><p role="alert">{error}</p><button className="profile-detail-button" onClick={() => setRetry(value => value + 1)}>Try again</button></>
      : <p role="status">Loading your workspace…</p>}
  </div></main>;
}
