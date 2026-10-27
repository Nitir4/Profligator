import { useState } from "react";

type Identity = { handle: string; display_name?: string; avatar_url?: string | null };

export default function ProfileAvatar({ profile, className = "" }: { profile: Identity | null; className?: string }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const name = profile?.display_name || profile?.handle || "Profile";
  const initials = name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
  return <span className={`profile-avatar ${className}`} aria-hidden="true">
    {profile?.avatar_url && failedUrl !== profile.avatar_url
      ? <img src={profile.avatar_url} alt="" onError={() => setFailedUrl(profile.avatar_url ?? null)} />
      : initials}
  </span>;
}
