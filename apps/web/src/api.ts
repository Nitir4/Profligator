export type SupportedPlatform = "leetcode" | "geeksforgeeks" | "codeforces";
export type ConnectorMode = "fixture" | "official_api" | "aggregator" | "scraper";

export type PlatformProfile = {
  id: string;
  platform: SupportedPlatform;
  public_handle: string;
  canonical_url: string;
  verification_state: "verified" | "unverified" | "fixture_only";
  connector_mode: ConnectorMode;
  last_successful_sync: string | null;
  created_at: string;
  updated_at: string;
};

export type ConnectorDescriptor = {
  platform: SupportedPlatform;
  mode: ConnectorMode;
  live_data: boolean;
  notice: string;
};

export type SyncRun = {
  id: string;
  platform_profile_id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  records_seen: number;
  records_written: number;
  error_code: string | null;
  error_message: string | null;
};

export type DashboardData = {
  total_problems_solved: number;
  provisional_unique_problems: number;
  unique_problems_solved: number;
  matched_records: number;
  unmatched_records: number;
  semantic_matching: "disabled" | "enabled";
  records_with_statements: number;
  records_without_statements: number;
  matching_unavailable_records: number;
  exact_matched_records: number;
  semantic_matched_records: number;
  connected_profiles: number;
  platforms: Array<{
    verification_state: PlatformProfile["verification_state"];
    platform: SupportedPlatform;
    profile_handle: string;
    solved: number;
    source_total_solved: number | null;
    history_complete: boolean | null;
    rating: number | null;
    rank: string | null;
    contests_enabled: boolean;
    connector_mode: ConnectorMode;
    latest_sync_status: SyncRun["status"] | null;
    sync_error: string | null;
    last_successful_sync: string | null;
    source_difficulty_counts: Record<string, number> | null;
    activity_status: "available" | "partial" | "unavailable" | "unsupported";
    activity_years: number[];
    activity_available_years: number[];
    activity_error: string | null;
    questions_with_statements: number;
    questions_with_utc_dates: number;
    questions_with_source_times: number;
  }>;
  activity: {
    days: Array<{ date: string; count: number }>;
    known_timestamp_records: number;
    source_calendars?: { platform: SupportedPlatform; profile_handle: string; days: { date: string; count: number }[] }[];
    unknown_timestamp_records: number;
    current_streak: number;
    longest_streak: number;
    count_label: string;
    timezone: string;
    calendar_submissions: number;
    calendar_profiles: number;
  };
  topics: {
    items: Array<{ name: string; count: number; percent: number }>;
    total_assignments: number;
    records_without_topics: number;
  };
  difficulties: {
    items: Array<{ name: string; count: number; percent: number }>;
    rated_records: number;
    unrated_records: number;
  };
  data_state: "empty" | "partial" | "ready";
  partial_reasons: string[];
  last_successful_sync: string | null;
  generated_at: string;
  uniqueness_notice: string;
  contests: Array<{
    platform: SupportedPlatform;
    source_id: string;
    title: string;
    canonical_url: string;
    occurred_at: string | null;
    contest_rating: number | null;
    global_rank: number | null;
  }>;
};

export type AuthUser = {
  id: string;
  email: string;
  handle: string;
  display_name: string;
  bio: string;
  avatar_url: string | null;
  created_at: string;
  role: "candidate" | "recruiter";
  auth_provider: string;
};

export type AuthSession = {
  user: AuthUser;
  access_expires_at: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(
  /\/$/,
  "",
);

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code?: string,
  ) {
    super(message);
  }
}

let refreshInFlight: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = fetch(`${API_BASE_URL}/api/v1/auth/refresh`, { method: "POST", credentials: "include" })
      .then(response => response.ok).catch(() => false).finally(() => { refreshInFlight = null; });
  }
  return refreshInFlight;
}

async function apiRequest<T>(
  path: string,
  init?: RequestInit,
  retryAfterRefresh = true,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch {
    throw new ApiError("The Profligator API is unavailable.", 0, "network_error");
  }

  const payload = await response.json().catch(() => null);
  if (
    response.status === 401 &&
    retryAfterRefresh &&
    ![
      "/api/v1/auth/register",
      "/api/v1/auth/login",
      "/api/v1/auth/refresh",
      "/api/v1/auth/logout",
    ].includes(path)
  ) {
    if (await refreshSession()) return apiRequest(path, init, false);
  }
  if (!response.ok) {
    const detail = payload?.error ?? payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail?.message ?? "The API request could not be completed.";
    throw new ApiError(message, response.status, detail?.code);
  }
  return payload as T;
}

export function registerCandidate(
  email: string,
  handle: string,
  password: string,
): Promise<AuthSession> {
  return apiRequest("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, handle, password }),
  });
}

export function loginCandidate(email: string, password: string): Promise<AuthSession> {
  return apiRequest("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export function requestPasswordReset(email: string): Promise<{ message: string }> {
  return apiRequest("/api/v1/auth/forgot-password", {
    method: "POST", body: JSON.stringify({ email }),
  }, false);
}

export function resetPassword(token: string, password: string, confirmPassword: string): Promise<{ message: string }> {
  return apiRequest("/api/v1/auth/reset-password", {
    method: "POST", body: JSON.stringify({ token, password, confirm_password: confirmPassword }),
  }, false);
}

export type AuthProviders = {
  google_configured: boolean;
  google_connected: boolean;
  google_email: string | null;
  password_enabled: boolean;
};

export function getAuthProviders(): Promise<AuthProviders> {
  return apiRequest("/api/v1/auth/providers");
}

export async function startGoogleAuth(linkAccount = false): Promise<void> {
  const result = await apiRequest<{ authorization_url: string }>(
    linkAccount ? "/api/v1/auth/google/link" : "/api/v1/auth/google/start",
    { method: "POST" },
  );
  window.location.assign(result.authorization_url);
}

const googleErrors: Record<string, string> = {
  google_not_configured: "Google sign-in is not configured yet.",
  google_cancelled: "Google sign-in was cancelled. You can try again.",
  invalid_state: "This Google sign-in attempt expired or was already used. Please try again.",
  invalid_identity: "Google could not verify your sign-in. Please try again.",
  google_unavailable: "Google is temporarily unavailable. Please try again.",
  google_exchange_failed: "Google sign-in could not complete. Please try again.",
  account_exists: "An account with this email already exists. Sign in with your password, then connect Google in Account settings.",
  google_already_linked: "This Google account is already connected to another account, or your account has another Google connection.",
  link_session_expired: "Your account session changed or expired. Sign in again before connecting Google.",
  account_conflict: "An account connection changed during sign-in. Please try again.",
};

export function googleAuthError(): string | null {
  const code = new URLSearchParams(window.location.search).get("google_error");
  return code ? googleErrors[code] ?? "Google sign-in could not complete. Please try again." : null;
}

export function getCurrentUser(): Promise<AuthUser> {
  return apiRequest("/api/v1/auth/me");
}

export function updateAccountProfile(profile: { handle: string; display_name: string; bio: string }): Promise<AuthUser> {
  return apiRequest("/api/v1/account/profile", { method: "PUT", body: JSON.stringify(profile) });
}

export function uploadProfilePhoto(file: File): Promise<AuthUser> {
  return apiRequest("/api/v1/account/avatar", { method: "PUT", body: file, headers: { "Content-Type": file.type } });
}

export function removeProfilePhoto(): Promise<AuthUser> {
  return apiRequest("/api/v1/account/avatar", { method: "DELETE" });
}

export async function logoutCandidate(): Promise<void> {
  await apiRequest("/api/v1/auth/logout", { method: "POST" }, false);
}

export function listPlatformProfiles(): Promise<PlatformProfile[]> {
  return apiRequest("/api/v1/platform-profiles");
}

export function listConnectors(): Promise<ConnectorDescriptor[]> {
  return apiRequest("/api/v1/connectors");
}

export function checkPlatformProfile(
  platform: SupportedPlatform,
  handleOrUrl: string,
): Promise<{
  profile: { platform: SupportedPlatform; handle: string; canonical_url: string; display_name: string | null };
  mode: ConnectorMode;
  live_data: boolean;
  notice: string;
}> {
  return apiRequest("/api/v1/platform-profiles/check", {
    method: "POST",
    body: JSON.stringify({ platform, handle_or_url: handleOrUrl }),
  });
}

export function linkPlatformProfile(
  platform: SupportedPlatform,
  handleOrUrl: string,
): Promise<PlatformProfile> {
  return apiRequest("/api/v1/platform-profiles", {
    method: "POST",
    body: JSON.stringify({ platform, handle_or_url: handleOrUrl }),
  });
}

export async function disconnectPlatformProfile(platformProfileId: string): Promise<void> {
  await apiRequest(`/api/v1/platform-profiles/${encodeURIComponent(platformProfileId)}`, {
    method: "DELETE",
  });
}

export function startProfileSync(platformProfileId: string): Promise<SyncRun> {
  return apiRequest("/api/v1/syncs", {
    method: "POST",
    body: JSON.stringify({ platform_profile_id: platformProfileId }),
  });
}

export function getSync(syncId: string): Promise<SyncRun> {
  return apiRequest(`/api/v1/syncs/${encodeURIComponent(syncId)}`);
}

export async function waitForSync(
  initial: SyncRun,
  timeoutMs = 120_000,
): Promise<SyncRun> {
  let run = initial;
  const deadline = Date.now() + timeoutMs;
  while (run.status === "pending" || run.status === "running") {
    if (Date.now() >= deadline) {
      throw new ApiError("Profile sync is still running. Check the dashboard shortly.", 408);
    }
    await new Promise((resolve) => window.setTimeout(resolve, 750));
    run = await getSync(run.id);
  }
  if (run.status === "failed") {
    throw new ApiError(run.error_message ?? "Profile sync failed.", 422, run.error_code ?? undefined);
  }
  return run;
}

export function getDashboard(): Promise<DashboardData> {
  return apiRequest("/api/v1/dashboard");
}

export type SolvedProblem = {
  id: string;
  platform: SupportedPlatform;
  profile_handle: string;
  source_id: string;
  title: string;
  canonical_url: string;
  submission_url: string | null;
  difficulty: string | null;
  topics: string[];
  solved_at: string | null;
  source_solved_at: string | null;
  has_statement: boolean;
};

export type SolvedProblemPage = { items: SolvedProblem[]; total: number; offset: number; limit: number };

export function getSolvedProblems(
  filters: { offset: number; limit: number; search: string; platform: string; difficulty: string },
  shareToken?: string,
): Promise<SolvedProblemPage> {
  const query = new URLSearchParams({ offset: String(filters.offset), limit: String(filters.limit) });
  if (filters.search) query.set("search", filters.search);
  if (filters.platform) query.set("platform", filters.platform);
  if (filters.difficulty) query.set("difficulty", filters.difficulty);
  const path = shareToken ? `/api/v1/public-profiles/${encodeURIComponent(shareToken)}/solved-problems` : "/api/v1/solved-problems";
  return apiRequest(`${path}?${query}`, undefined, !shareToken);
}

export type SharingSettings = { enabled: boolean; shareable_link: string | null };
export type PublicProfile = { handle: string; display_name: string; bio: string; avatar_url: string | null; dashboard: DashboardData };

export function getSharing(): Promise<SharingSettings> {
  return apiRequest("/api/v1/sharing");
}

export function updateSharing(enabled: boolean): Promise<SharingSettings> {
  return apiRequest("/api/v1/sharing", { method: "PUT", body: JSON.stringify({ enabled }) });
}

export function getPublicProfile(token: string): Promise<PublicProfile> {
  return apiRequest(`/api/v1/public-profiles/${encodeURIComponent(token)}`, undefined, false);
}

export type ExtensionSession = { id: string; label: string; created_at: string; expires_at: string };

export function getExtensionSessions(): Promise<ExtensionSession[]> {
  return apiRequest("/api/v1/extension/sessions");
}

export async function revokeExtensionSession(id: string): Promise<void> {
  await apiRequest(`/api/v1/extension/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export type VerificationStatus = { email: string; email_verified: boolean; email_delivery_configured: boolean };
export function getVerificationStatus(): Promise<VerificationStatus> { return apiRequest("/api/v1/auth/verification"); }
export function requestEmailVerification(): Promise<{ message: string }> {
  return apiRequest("/api/v1/auth/verification/request", { method: "POST" });
}
export function confirmEmailVerification(token: string): Promise<{ message: string }> {
  return apiRequest("/api/v1/auth/verification/confirm", { method: "POST", body: JSON.stringify({ token }) });
}
export type OwnershipChallenge = { challenge: string; instructions: string; expires_in_minutes: number };
export function requestOwnershipChallenge(id: string): Promise<OwnershipChallenge> {
  return apiRequest(`/api/v1/platform-profiles/${encodeURIComponent(id)}/ownership/challenge`, { method: "POST" });
}
export function confirmProfileOwnership(id: string, challenge: string): Promise<{ message: string }> {
  return apiRequest(`/api/v1/platform-profiles/${encodeURIComponent(id)}/ownership/confirm`, { method: "POST", body: JSON.stringify({ challenge }) });
}
