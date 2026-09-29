export type SupportedPlatform = "leetcode" | "geeksforgeeks" | "codeforces";

export type PlatformProfile = {
  id: string;
  platform: SupportedPlatform;
  public_handle: string;
  canonical_url: string;
  verification_state: "verified" | "unverified" | "fixture_only";
  connector_mode: "fixture" | "official_api";
  last_successful_sync: string | null;
  created_at: string;
  updated_at: string;
};

export type ConnectorDescriptor = {
  platform: SupportedPlatform;
  mode: "fixture" | "official_api";
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
  connected_profiles: number;
  platforms: Array<{
    platform: SupportedPlatform;
    profile_handle: string;
    solved: number;
    last_successful_sync: string | null;
  }>;
  activity: {
    days: Array<{ date: string; count: number }>;
    known_timestamp_records: number;
    unknown_timestamp_records: number;
    current_streak: number;
    longest_streak: number;
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
};

export type AuthUser = {
  id: string;
  email: string;
  handle: string;
  created_at: string;
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
    const refreshed = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });
    if (refreshed.ok) return apiRequest(path, init, false);
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

export function getCurrentUser(): Promise<AuthUser> {
  return apiRequest("/api/v1/auth/me");
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
): Promise<unknown> {
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
