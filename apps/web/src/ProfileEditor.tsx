import { FormEvent, useRef, useState } from "react";
import { AuthUser, removeProfilePhoto, updateAccountProfile, uploadProfilePhoto } from "./api";
import ProfileAvatar from "./ProfileAvatar";

export default function ProfileEditor({ user, onUpdated }: { user: AuthUser; onUpdated: (user: AuthUser) => void }) {
  const [name, setName] = useState(user.display_name || "");
  const [handle, setHandle] = useState(user.handle);
  const [bio, setBio] = useState(user.bio || "");
  const [saving, setSaving] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const photoInput = useRef<HTMLInputElement>(null);

  async function save(event: FormEvent) {
    event.preventDefault(); setSaving(true); setError(""); setNotice("");
    try {
      const updated = await updateAccountProfile({ handle, display_name: name, bio });
      onUpdated(updated); setName(updated.display_name); setHandle(updated.handle); setBio(updated.bio);
      setNotice("Profile updated.");
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Could not save your profile."); }
    finally { setSaving(false); }
  }

  async function changePhoto(file?: File) {
    setError(""); setNotice("");
    if (file && (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 4 * 1024 * 1024)) {
      setError("Choose a JPEG, PNG or WebP photo smaller than 4 MB."); return;
    }
    setPhotoBusy(true);
    try { onUpdated(file ? await uploadProfilePhoto(file) : await removeProfilePhoto()); setNotice(file ? "Profile photo updated." : "Profile photo removed."); }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not update your photo."); }
    finally { setPhotoBusy(false); }
  }

  return <section className="settings-card profile-editor" id="profile" aria-labelledby="profile-editor-title">
    <div className="settings-card-heading"><h2 id="profile-editor-title">Your profile</h2><p>Choose how you appear in Profligator and on your shared profile.</p></div>
    <div className="profile-photo-editor">
      <ProfileAvatar profile={user} className="profile-photo-large" />
      <div><div className="profile-photo-actions">
        <button className="profile-detail-button" type="button" disabled={photoBusy || saving} onClick={() => photoInput.current?.click()}>{photoBusy ? "Updating photo…" : "Upload photo"}</button>
        {user.avatar_url && <button className="profile-detail-button" type="button" disabled={photoBusy || saving} onClick={() => void changePhoto()}>Remove photo</button>}
        <input ref={photoInput} type="file" hidden aria-label="Upload profile photo" accept="image/jpeg,image/png,image/webp" onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file) void changePhoto(file); }} />
      </div><p>JPEG, PNG or WebP · up to 4 MB. Photos are cropped to a square.</p></div>
    </div>
    <form onSubmit={save} className="profile-edit-form">
      <div className="profile-edit-fields">
        <label htmlFor="profile-display-name">Display name<input id="profile-display-name" maxLength={80} value={name} disabled={saving} onChange={(event) => { setName(event.target.value); setError(""); setNotice(""); }} placeholder="Your name" autoComplete="name" /></label>
        <div className="profile-edit-field"><label htmlFor="profile-username">Username</label><input id="profile-username" required minLength={3} maxLength={64} pattern="[A-Za-z0-9_.\-]+" value={handle} disabled={saving} onChange={(event) => { setHandle(event.target.value); setError(""); setNotice(""); }} aria-describedby="username-help" autoComplete="username" /><small id="username-help">3–64 letters, numbers, dots, underscores or hyphens. Unique regardless of letter case.</small></div>
      </div>
      <div className="profile-edit-field"><label htmlFor="profile-bio">Short bio</label><textarea id="profile-bio" rows={3} maxLength={280} value={bio} disabled={saving} onChange={(event) => { setBio(event.target.value); setError(""); setNotice(""); }} placeholder="A little about you and what you're working on" aria-describedby="profile-bio-count" /><small id="profile-bio-count">{bio.length}/280</small></div>
      {error && <p className="profile-fetch-error" role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      <div className="profile-edit-footer"><p>Your sign-in email and linked coding accounts stay the same.</p><button className="profile-detail-button profile-save-button" type="submit" disabled={saving || photoBusy}>{saving ? "Saving…" : "Save profile"}</button></div>
    </form>
  </section>;
}
