import { FormEvent, useMemo, useState } from "react";
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
  id: number;
  platform: PlatformKey;
  handle: string;
  verified: boolean;
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

const initialProfiles: Profile[] = [
  { id: 1, platform: "leetcode", handle: "alex_dev96", verified: true },
  {
    id: 2,
    platform: "geeksforgeeks",
    handle: "alexander_codes",
    verified: true,
  },
];

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
              verified: false,
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
            onChange({ ...profile, handle: event.target.value, verified: false })
          }
        />
        {profile.verified && (
          <span className="verified-badge">
            <img src={verifiedIcon} alt="" />
            <span>Verified</span>
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
  const [profiles, setProfiles] = useState<Profile[]>(initialProfiles);
  const [saved, setSaved] = useState(false);
  const [checking, setChecking] = useState(false);

  const nextId = useMemo(
    () => Math.max(0, ...profiles.map((profile) => profile.id)) + 1,
    [profiles],
  );

  function addProfile(platform: PlatformKey = "codeforces") {
    setSaved(false);
    setProfiles((current) => [
      ...current,
      { id: nextId, platform, handle: "", verified: false },
    ]);
  }

  function checkAll() {
    setChecking(true);
    window.setTimeout(() => {
      setProfiles((current) =>
        current.map((profile) => ({
          ...profile,
          verified: profile.handle.trim().length > 0,
        })),
      );
      setChecking(false);
    }, 450);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaved(true);
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
                AD
              </span>
              <span>alex@example.com</span>
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
              <button className="check-all-button" type="button" onClick={checkAll}>
                <img src={refreshIcon} alt="" />
                <span>{checking ? "Checking…" : "Check all"}</span>
              </button>
            </div>

            <div className="profile-rows" aria-live="polite">
              {profiles.map((profile) => (
                <ProfileRow
                  key={profile.id}
                  profile={profile}
                  onChange={(nextProfile) => {
                    setSaved(false);
                    setProfiles((current) =>
                      current.map((item) =>
                        item.id === nextProfile.id ? nextProfile : item,
                      ),
                    );
                  }}
                  onRemove={() => {
                    setSaved(false);
                    setProfiles((current) =>
                      current.filter((item) => item.id !== profile.id),
                    );
                  }}
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
              <p>
                {saved
                  ? "Your profiles have been saved."
                  : "You can modify, add, or disconnect profiles at any time in Settings."}
              </p>
              <div className="profile-actions">
                <a href="/dashboard">Skip for now</a>
                <button className="save-profiles-button" type="submit">
                  <span>Save &amp; Continue to Dashboard</span>
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
