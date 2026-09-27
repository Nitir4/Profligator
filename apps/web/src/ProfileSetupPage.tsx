import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  AuthUser,
  checkPlatformProfile,
  disconnectPlatformProfile,
  getCurrentUser,
  linkPlatformProfile,
  listPlatformProfiles,
  startProfileSync,
  SupportedPlatform,
  waitForSync,
} from "./api";
import addIcon from "./assets/profiles/add.svg";
import chevronDownIcon from "./assets/profiles/chevron-down.svg";
import continueArrowIcon from "./assets/profiles/continue-arrow.svg";
import documentationIcon from "./assets/profiles/documentation.svg";
import geeksForGeeksIcon from "./assets/profiles/geeksforgeeks.svg";
import leetCodeIcon from "./assets/profiles/leetcode.svg";
import privacyShieldIcon from "./assets/profiles/privacy-shield.svg";
import profileLogo from "./assets/profiles/profile-logo.png";
import refreshIcon from "./assets/profiles/refresh.svg";
import selectArtIcon from "./assets/profiles/select-art.svg";
import trashIcon from "./assets/profiles/trash.svg";
import verifiedIcon from "./assets/profiles/verified.svg";

type PlatformKey =
  | "leetcode"
  | "geeksforgeeks"
  | "codeforces"
  | "codechef"
  | "hackerrank"
  | "atcoder"
  | "kaggle"
  | "github";

type Profile = {
  id: string;
  platform: PlatformKey;
  handle: string;
  state: "unchecked" | "ready" | "verified" | "fixture_only";
};

const platformDetails: Record<
  PlatformKey,
  { label: string; prefix: string; icon?: string }
> = {
  leetcode: { label: "LeetCode", prefix: "leetcode.com/u/", icon: leetCodeIcon },
  geeksforgeeks: {
    label: "GeeksforGeeks",
    prefix: "geeksforgeeks.org/user/",
    icon: geeksForGeeksIcon,
  },
  codeforces: { label: "Codeforces", prefix: "codeforces.com/profile/" },
  codechef: { label: "CodeChef", prefix: "codechef.com/users/" },
  hackerrank: { label: "HackerRank", prefix: "hackerrank.com/profile/" },
  atcoder: { label: "AtCoder", prefix: "atcoder.jp/users/" },
  kaggle: { label: "Kaggle", prefix: "kaggle.com/" },
  github: { label: "GitHub", prefix: "github.com/" },
};

const quickPlatforms: PlatformKey[] = [
  "codeforces",
  "codechef",
  "hackerrank",
  "atcoder",
  "kaggle",
  "github",
];

const supportedPlatforms = new Set<PlatformKey>([
  "leetcode",
  "geeksforgeeks",
  "codeforces",
]);

function isSupportedPlatform(platform: PlatformKey): platform is SupportedPlatform {
  return supportedPlatforms.has(platform);
}

function ProfileRow({
  profile,
  onChange,
  onRemove,
}: {
  profile: Profile;
  onChange: (profile: Profile) => void;
  onRemove: () => void;
}) {
  const platform = platformDetails[profile.platform];

  return (
    <div className="profile-row">
      <label className="platform-select-wrap">
        <span className="sr-only">Coding platform</span>
        {platform.icon ? (
          <img className="platform-icon" src={platform.icon} alt="" />
        ) : (
          <span className="platform-fallback" aria-hidden="true">
            {platform.label.slice(0, 1)}
          </span>
        )}
        <select
          value={profile.platform}
          onChange={(event) =>
            onChange({
              ...profile,
              platform: event.target.value as PlatformKey,
              state: "unchecked",
            })
          }
        >
          {Object.entries(platformDetails).map(([key, details]) => (
            <option key={key} value={key}>
              {details.label}
            </option>
          ))}
        </select>
        <span className="select-icons" aria-hidden="true">
          <img className="select-art" src={selectArtIcon} alt="" />
          <img className="select-chevron" src={chevronDownIcon} alt="" />
        </span>
      </label>

      <label className="profile-url-field">
        <span className="sr-only">{platform.label} username</span>
        <span className="profile-prefix" aria-hidden="true">
          {platform.prefix}
        </span>
        <input
          value={profile.handle}
          spellCheck={false}
          onChange={(event) =>
            onChange({ ...profile, handle: event.target.value, state: "unchecked" })
          }
        />
        {profile.state !== "unchecked" && (
          <span className="verified-badge">
            <img src={verifiedIcon} alt="" />
            <span>
              {profile.state === "fixture_only"
                ? "Fixture"
                : profile.state === "ready"
                  ? "Ready"
                  : "Verified"}
            </span>
          </span>
        )}
      </label>

      <button
        className="remove-profile-button"
        type="button"
        aria-label={`Remove ${platform.label} profile`}
        onClick={onRemove}
      >
        <img src={trashIcon} alt="" />
      </button>
    </div>
  );
}

function ProfileSetupPage() {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [saved, setSaved] = useState(false);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("Loading connected profiles…");
  const [removedProfileIds, setRemovedProfileIds] = useState<string[]>([]);
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((currentUser) => {
        if (!active) return [];
        setUser(currentUser);
        return listPlatformProfiles();
      })
      .then((savedProfiles) => {
        if (!active) return;
        setProfiles(
          savedProfiles.length > 0
            ? savedProfiles.map((profile) => ({
                id: profile.id,
                platform: profile.platform,
                handle: profile.public_handle,
                state:
                  profile.verification_state === "fixture_only"
                    ? "fixture_only"
                    : profile.verification_state === "verified"
                      ? "verified"
                      : "unchecked",
              }))
            : [
                {
                  id: "local-codeforces",
                  platform: "codeforces",
                  handle: "",
                  state: "unchecked",
                },
              ],
        );
        setMessage("You can modify, add, or disconnect profiles at any time in Settings.");
      })
      .catch((error: ApiError) => {
        if (!active) return;
        if (error.status === 401) {
          window.location.assign("/login");
          return;
        }
        setProfiles([
          {
            id: "local-codeforces",
            platform: "codeforces",
            handle: "",
            state: "unchecked",
          },
        ]);
        setMessage(error.message);
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, []);

  function addProfile(platform: PlatformKey = "codeforces") {
    setSaved(false);
    setProfiles((current) => [
      ...current,
      {
        id: `local-${Date.now()}-${current.length}`,
        platform,
        handle: "",
        state: "unchecked",
      },
    ]);
  }

  function updateProfile(currentProfile: Profile, nextProfile: Profile) {
    setSaved(false);
    let replacement = nextProfile;
    if (
      !currentProfile.id.startsWith("local-") &&
      (currentProfile.platform !== nextProfile.platform ||
        currentProfile.handle !== nextProfile.handle)
    ) {
      setRemovedProfileIds((current) =>
        current.includes(currentProfile.id) ? current : [...current, currentProfile.id],
      );
      replacement = { ...nextProfile, id: `local-${Date.now()}` };
    }
    setProfiles((current) =>
      current.map((item) => (item.id === currentProfile.id ? replacement : item)),
    );
  }

  function removeProfile(profile: Profile) {
    setSaved(false);
    if (!profile.id.startsWith("local-")) {
      setRemovedProfileIds((current) =>
        current.includes(profile.id) ? current : [...current, profile.id],
      );
    }
    setProfiles((current) => current.filter((item) => item.id !== profile.id));
  }

  async function checkAll() {
    setChecking(true);
    setMessage("Checking profile handles…");
    try {
      const checked = await Promise.all(
        profiles.map(async (profile) => {
          if (!profile.handle.trim()) return profile;
          if (!isSupportedPlatform(profile.platform)) {
            throw new ApiError(`${platformDetails[profile.platform].label} is not supported yet.`, 422);
          }
          await checkPlatformProfile(profile.platform, profile.handle.trim());
          return {
            ...profile,
            state: profile.platform === "codeforces" ? "ready" : "fixture_only",
          } as Profile;
        }),
      );
      setProfiles(checked);
      setMessage("Profile checks completed.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Profile checks failed.");
    } finally {
      setChecking(false);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setSaved(false);
    setMessage("Saving profiles and starting synchronization…");
    try {
      await Promise.all(removedProfileIds.map(disconnectPlatformProfile));
      const populated = profiles.filter((profile) => profile.handle.trim());
      for (const profile of populated) {
        if (!isSupportedPlatform(profile.platform)) {
          throw new ApiError(`${platformDetails[profile.platform].label} is not supported yet.`, 422);
        }
        const linked = await linkPlatformProfile(profile.platform, profile.handle.trim());
        const run = await startProfileSync(linked.id);
        await waitForSync(run);
      }
      setSaved(true);
      setMessage("Profiles synchronized. Opening your dashboard…");
      window.setTimeout(() => window.location.assign("/dashboard"), 250);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Profiles could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="profiles-page" data-node-id="2603:2059">
      <header className="setup-header" data-node-id="2603:2207">
        <div className="setup-header-inner">
          <a className="setup-brand" href="/login" aria-label="Profligator home">
            <img src={profileLogo} alt="" />
            <span>Profligator</span>
          </a>

          <div className="setup-header-actions">
            <a className="setup-docs-link" href="#documentation">
              <img src={documentationIcon} alt="" />
              <span>Documentation</span>
            </a>
            <span className="header-divider" aria-hidden="true" />
            <div className="account-chip">
              <span className="account-avatar" aria-hidden="true">
                {(user?.handle ?? "C").slice(0, 2).toUpperCase()}
              </span>
              <span>{user?.email ?? "Loading…"}</span>
            </div>
          </div>
        </div>
      </header>

      <main className="profiles-main">
        <div className="profiles-content">
          <section className="profiles-intro" aria-labelledby="profiles-title">
            <div className="breadcrumb" aria-label="Breadcrumb">
              <span>Onboarding</span>
              <span aria-hidden="true">/</span>
              <span>Connect Profiles</span>
            </div>
            <h1 id="profiles-title">Add your coding profiles</h1>
            <p className="profiles-description">
              Connect your public handles from LeetCode, Codeforces, GitHub, and more.
              Profligator will
              <br />
              aggregate your solved problems, contest ratings, and submission activity into a
              single portfolio.
            </p>
            <p className="privacy-note">
              <img src={privacyShieldIcon} alt="" />
              <span>Only public metrics are fetched. We never ask for passwords or API tokens.</span>
            </p>
          </section>

          <form className="profiles-card" onSubmit={handleSubmit} data-node-id="2603:2080">
            <div className="profiles-card-header">
              <div className="connected-heading">
                <h2>Connected Accounts</h2>
                <span>{profiles.length} profiles</span>
              </div>
              <button
                className="check-all-button"
                type="button"
                onClick={checkAll}
                disabled={loading || checking || saving}
              >
                <img src={refreshIcon} alt="" />
                <span>{checking ? "Checking…" : "Check all"}</span>
              </button>
            </div>

            <div className="profile-rows" aria-live="polite">
              {profiles.map((profile) => (
                <ProfileRow
                  key={profile.id}
                  profile={profile}
                  onChange={(nextProfile) => updateProfile(profile, nextProfile)}
                  onRemove={() => removeProfile(profile)}
                />
              ))}
            </div>

            <div className="add-platform-section">
              <button className="add-platform-button" type="button" onClick={() => addProfile()}>
                <img src={addIcon} alt="" />
                <span>Add another platform</span>
              </button>
              <div className="quick-platforms">
                <span className="quick-platforms-label">Popular platforms:</span>
                {quickPlatforms.map((platform) => (
                  <button
                    key={platform}
                    type="button"
                    onClick={() => addProfile(platform)}
                  >
                    <span aria-hidden="true">+</span>
                    <span>{platformDetails[platform].label}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="profiles-card-footer">
              <p role="status">{saved ? "Your profiles have been saved." : message}</p>
              <div className="profile-actions">
                <a href="/dashboard">Skip for now</a>
                <button
                  className="save-profiles-button"
                  type="submit"
                  disabled={loading || saving || checking}
                >
                  <span>{saving ? "Synchronizing…" : "Save & Continue to Dashboard"}</span>
                  <img src={continueArrowIcon} alt="" />
                </button>
              </div>
            </div>
          </form>
        </div>
      </main>

      <footer className="setup-footer" data-node-id="2603:2194">
        <div className="setup-footer-inner">
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

export default ProfileSetupPage;
