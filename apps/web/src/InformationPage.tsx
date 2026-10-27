import { useEffect, useState } from "react";
import { AuthUser, getCurrentUser } from "./api";
import { WorkspaceFooter, WorkspaceHeader } from "./WorkspaceChrome";

export const informationTitles: Record<string, string> = {
  "/documentation": "Getting started", "/privacy": "Privacy", "/terms": "Terms of use",
  "/status": "Service status", "/support": "Contact support",
};

const contact = <a href="https://github.com/Nitir4/Profligator/issues" target="_blank" rel="noopener noreferrer">the project issue tracker</a>;

export default function InformationPage({ path }: { path: string }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  useEffect(() => {
    let active = true;
    getCurrentUser().then((account) => { if (active) setUser(account); }).catch(() => {});
    return () => { active = false; };
  }, []);
  return <div className="dashboard-page information-page">
    {user ? <WorkspaceHeader user={user} activeTab="account" /> : null}
    <nav className="information-nav" aria-label="Information pages">
      {!user && <a href="/dashboard" aria-label="Profligator home">Profligator</a>}
      {Object.entries(informationTitles).map(([href, title]) => <a key={href} href={href} aria-current={path === href ? "page" : undefined}>{title}</a>)}
    </nav>
    <main className="dashboard-main"><article className="dashboard-content information-content">
      <h1>{informationTitles[path]}</h1>
      {path === "/documentation" && <>
        <p>Profligator brings your available coding history into one profile and checks questions against your saved solves.</p>
        <h2>Set up your profile</h2><ol>
          <li><a href="/login">Create an account or sign in</a> with your password or configured Google sign-in.</li>
          <li>Open Profiles, add your LeetCode, GeeksforGeeks or Codeforces handle, check availability, and save.</li>
          <li>Open the dashboard to refresh your history. Source totals and imported questions can differ when a platform hides older records.</li>
          <li>Open <a href="/settings/account">Account settings</a> to verify your email and prove control of your linked profiles.</li>
          <li>Connect the browser extension from <a href="/extension/connect">Browser connections</a>. Use the extension popup to import supported history and check opened questions.</li>
        </ol>
        <h2>Share with care</h2><p>Enable sharing in <a href="/settings/sharing">Sharing settings</a>, then copy your link. Anyone with an active link can view the shared profile. Turn sharing off to revoke access.</p>
        <h2>Understand the results</h2><p>Dates, statements and attempt links depend on the source. A missing duplicate alert does not prove a question is new. Semantic matching depends on configuration, coverage and provider availability.</p>
        <p>Forgot your password? <a href="/forgot-password">Request a reset link</a>. For help, use {contact}.</p>
      </>}
      {path === "/privacy" && <>
        <p className="information-notice">Draft privacy notice for the project preview. Last updated 13 October 2026.</p>
        <h2>Information used by the app</h2><p>Profligator stores account details, a password hash when password sign-in is used, linked coding handles, available coding activity, sync results and matching decisions. Google sign-in stores the identity needed to connect your account. Authentication uses cookies; connected extensions use separately revocable sessions.</p>
        <h2>Collection and matching</h2><p>Public collectors request data from the coding platforms you link. Owner-authorized extension imports can add available solved history and public problem text. When hosted semantic matching is enabled, question titles, statements and topics are sent to the configured model provider for comparison.</p>
        <h2>Email and sharing</h2><p>Verification and password-reset emails are sent through configured mail providers. Sharing is opt-in: an active link exposes the coding profile to anyone who has it. Revocation stops future access through that link, but cannot erase copies someone already saved.</p>
        <h2>Your choices</h2><p>You can disconnect coding profiles, revoke browser connections and disable sharing in the app. For general account-data questions, use {contact}. Do not post personal account details in a public issue. Deletion requests require a private channel arranged with the project maintainers.</p>
      </>}
      {path === "/terms" && <>
        <p className="information-notice">Draft terms for the project preview. Last updated 13 October 2026.</p>
        <h2>Using Profligator</h2><p>Use accounts and coding profiles you are authorized to manage. Do not impersonate another person, submit false ownership evidence, abuse collection endpoints, or attempt to access another user's private history.</p>
        <h2>Data and results</h2><p>Coding platforms control the availability of their data. Imported history may be incomplete, and duplicate detection can miss matches or identify a pair incorrectly. Review the source evidence before using a profile or matching result to make a decision.</p>
        <h2>Sharing and third-party services</h2><p>You decide whether to share your profile and whom to give the link to. Coding platforms, Google sign-in, email providers and model providers have their own terms. Profligator is an independent project and does not represent those platforms.</p>
        <h2>Preview availability</h2><p>This preview may change or become unavailable. No uptime or completeness guarantee is offered. Questions about these draft terms can be raised in {contact}.</p>
      </>}
      {path === "/status" && <>
        <p className="information-notice">This is a placeholder status page. Automated service monitoring is not connected.</p>
        <p>There is no verified uptime or incident feed to show yet. This page does not establish the health of the API, email delivery, collectors, sync workers or matching provider.</p>
        <p>If an operation fails, keep the error message and time of the failure and use {contact}. Avoid posting personal details, passwords, reset links or access tokens.</p>
      </>}
      {path === "/support" && <>
        <p>For help with sign-in, profile imports, sharing or the browser extension, use {contact}.</p>
        <h2>What to include</h2><p>Describe what you expected, what happened, your browser and the affected coding platform. Include the error message and approximate time if available. Public issues are visible to others; do not include personal account details, passwords, SMTP credentials, authentication tokens or reset links.</p>
        <p>Support is handled manually; no response-time commitment is currently offered.</p>
      </>}
    </article></main><WorkspaceFooter />
  </div>;
}
