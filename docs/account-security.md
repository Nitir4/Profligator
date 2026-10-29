# Sign-in, email verification and coding-profile ownership

Source review: **15 November 2026**. These are separate workflows with different evidence. Configuration examples contain no actual operator mailbox or credentials.

## Sign-in and persistent access

Password sign-in uses the account's registered email and Argon2 password hash. Google sign-in is handled by the API's OAuth callback; client secrets stay server-side. To attach Google to an existing password account, sign into that account first and use **Account settings → Connect Google**. A matching email does not silently merge accounts.

The API issues a short-lived access cookie and a rotating refresh cookie. Defaults are 15 minutes and 30 days respectively. The browser can renew access during that refresh lifetime, including after a browser restart. Logout revokes the refresh session; clearing cookies, expiration, invalidation or a password reset can require signing in again. This is persistent access with an expiry, not an indefinite login promise.

Display name, username, bio and photo changes retain the immutable account ID. They do not rename coding-platform accounts, alter the registered email or disconnect Google. See [profile editing](account-profile.md).

## Verify the account inbox

1. Sign in and open **Account settings → Email verification**.
2. Request a verification email. Delivery must be enabled for the verification sender.
3. Open the one-use link while signed into the same Profligator account.
4. Confirm on the verification page and check the resulting account status.

Tokens expire after 30 minutes, are stored as hashes and are bound to the user, target email and authentication version. Requesting a replacement invalidates the previous pending token. The current request limit is three per user per hour. A successful request does not establish inbox receipt; check the mailbox and complete confirmation.

Google's verified-email claim establishes an OAuth identity claim. The app's account-inbox status is maintained separately in `verified_emails`; do not infer it merely from the presence of a Google connection.

## Prove control of a linked coding profile

Public availability only proves that a profile could be read. A successful synchronization or extension import also does not establish ownership.

1. Link the correct supported handle and verify your Profligator inbox first.
2. In account settings, create an ownership challenge for that linked profile.
3. Temporarily add the exact challenge to the provider's public name. For Codeforces, use its public first-name field as instructed by the app.
4. Save the change on the provider, then choose **Check public profile name** in Profligator.
5. After confirmation, restore the original public name on the provider.

The API reads the provider profile, checks the canonical handle and challenge boundary, and consumes the challenge before marking the linked profile verified. Challenges expire after 30 minutes. A provider failure or missing/wrong challenge never grants verification. Current per-user limits are ten challenge requests and twenty checks per hour.

The coding-platform email can differ from the Profligator email. The proof is control of a public profile field, not a comparison between two inbox addresses. A provider that cannot expose the challenge through its supported public profile response cannot be verified by guessing or by substituting an email claim.

## Recovery and separate senders

Recovery proves access to the registered account inbox and allows a password change. It uses the recovery sender. Account-inbox verification uses the independent verification sender. These sender accounts are delivery infrastructure, not the user's provider identity.

| Settings | Purpose |
| --- | --- |
| `PROFLIGATOR_PASSWORD_RESET_EMAIL_BACKEND`, `PROFLIGATOR_SMTP_*` | Password-reset mail and change notifications |
| `PROFLIGATOR_VERIFICATION_EMAIL_BACKEND`, `PROFLIGATOR_VERIFICATION_SMTP_*` | Account-inbox verification mail |
| `PROFLIGATOR_PUBLIC_WEB_URL` | Origin used in both sets of links |

Both backends default to disabled. Configure actual addresses/passwords only in an ignored environment file or private host settings. `scripts/configure_email.py --purpose verification`, `--purpose reset` or `--purpose both` prompts for sender credentials without storing defaults in source. Recovery details and loopback SMTP testing are in [password recovery](password-recovery.md).

## Browser and shared-profile authorization

**Connect this browser** grants a separately scoped, revocable extension session. It does not transfer Google credentials or coding-site cookies to the backend. The extension can check/import permitted history but cannot edit account identity or sharing settings using that scoped token.

A shared profile is readable only through its enabled random share token. It exposes chosen account identity and coding statistics, not the account's email or private credentials. Revocation blocks subsequent reads, including shared-photo access; it cannot recall a copy already downloaded.

## Relevant code and checks

- `security.py`: web-session validation and candidate/recruiter access.
- `google_auth.py`: state, nonce, PKCE, callback and explicit linking.
- `verification.py`: inbox proof, rate limits and provider-profile challenge checks.
- `password_recovery.py`: reset tokens, SMTP delivery and session invalidation.
- `extension_auth.py`: device-session grants, scope and revocation.
- `report_routes.py`: sharing consent and public data boundaries.

All API paths below use `/api/v1`:

| Method/path | Purpose |
| --- | --- |
| `GET /auth/verification` | Current account-inbox proof and delivery availability |
| `POST /auth/verification/request` | Send the account-inbox challenge |
| `POST /auth/verification/confirm` | Consume the inbox token |
| `POST /platform-profiles/{id}/ownership/challenge` | Create a linked-profile proof |
| `POST /platform-profiles/{id}/ownership/confirm` | Observe/consume the public-name proof |

Use `test_google_auth.py`, `test_verification.py`, `test_password_recovery.py` and `test_extension_auth.py` for deterministic regression. These tests do not send real provider emails. See [testing](testing.md) for commands and remaining real-account acceptance.
