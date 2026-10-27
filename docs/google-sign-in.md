# Google sign-in

Implemented on 2 October 2026. Standard Sign in with Google uses a free Google Cloud project/OAuth client, as described in [Google's setup codelab](https://codelabs.developers.google.com/codelabs/sign-in-with-google-button). This integration uses Google's [OpenID Connect server flow](https://developers.google.com/identity/openid-connect/openid-connect).

## Create the Google client

1. Open [Google Cloud Console](https://console.cloud.google.com/) and select or create a project for Profligator.
2. In **Google Auth Platform → Branding**, enter the app name, support email and contact details.
3. Configure **Audience** for the accounts you want to support. While testing an external app, add your own Google account as a test user if the console requests it.
4. In **Clients**, create an OAuth client with application type **Web application**.
5. Add the authorized redirect URI for the local web origin you actually use:

   ```text
   http://localhost:5173/api/v1/auth/google/callback
   ```

   For the separate sample preview on port 5174, use `http://localhost:5174/api/v1/auth/google/callback` instead. `localhost` and `127.0.0.1` are different hosts; use the exact same host throughout sign-in. Google must register each URI you use.

6. Save the client ID and client secret locally. Keep the secret out of frontend environment variables and committed files.

No browser Google SDK or JavaScript origin entry is required for this server redirect flow. The redirect URI is required. Production uses the HTTPS web origin with `/api/v1/auth/google/callback` routed to the API, consistent with the development Vite proxy.

## Configure Profligator

Create or edit `apps/api/.env` with these values (this file is ignored by Git):

```dotenv
PROFLIGATOR_GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
PROFLIGATOR_GOOGLE_CLIENT_SECRET=your-client-secret
PROFLIGATOR_PUBLIC_WEB_URL=http://localhost:5173
PROFLIGATOR_GOOGLE_REDIRECT_URI=http://localhost:5173/api/v1/auth/google/callback
```

The callback defaults to `PROFLIGATOR_PUBLIC_WEB_URL` plus `/api/v1/auth/google/callback`. It can be set explicitly. Restart the API after configuring credentials; settings are loaded at startup. If running the separate preview, use port 5174 consistently and note that exported process environment variables take precedence over `.env`.

Run `uv sync --project apps/api --dev` to install the signature-verification dependency. Existing migration-managed deployments must run `uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head`. The new migration adds OAuth identity/attempt tables and preserves existing users and coding records. Local development with automatic schema creation creates these tables on API startup.

## Sign-in behavior

- **New user:** Continue with Google creates a candidate with a unique generated handle, then opens profile onboarding.
- **Returning Google user:** identity lookup uses Google's stable `sub`, even if the Google email changes. Connected candidates go to the dashboard; other candidates go to onboarding; existing recruiters go to Team.
- **Existing password account:** Google sign-in does not merge accounts just because email matches. Sign in with your password, open **Account settings** from the user menu, and select **Connect Google**. This retains the user ID, handle, password, role, linked coding profiles and sharing settings.
- **Different Google email:** an explicitly signed-in user can connect a Google account with a different email. The original app email stays unchanged.
- **Cancelled/failed sign-in:** a clear error appears on the login/account page; an existing app session is preserved.
- **No credentials:** the login button reports that Google sign-in is not configured. Account settings shows the unavailable connection state.

## Implementation and verification

`POST /api/v1/auth/google/start` creates a short-lived attempt and an HttpOnly state cookie, and returns a Google authorization URL. `POST /api/v1/auth/google/link` creates a linking attempt for the authenticated user. Google calls `GET /api/v1/auth/google/callback`. `GET /api/v1/auth/providers` returns the authenticated account's connection status.

The server uses a random state, nonce and PKCE verifier. Attempts expire after ten minutes and are atomically consumed before the code exchange. PyJWT/cryptography verifies RS256 signatures against Google's cached public keys, issuer, audience, authorized presenter, timestamps, nonce and verified email. Google identity bindings have unique subject and account constraints. Linking checks that the same app user remains signed in. Google tokens and client secrets never enter browser URLs or application session responses; the app issues its own rotating session cookies.

Backend tests use real RSA signatures with synthetic keys and mocked Google HTTP responses. They cover new/returning users, explicit linking, stable identity, retained passwords, invalid claims/signatures, replay/expiry/state rejection, cancellation, service failures and migration preservation. All 70 backend tests and the production web build passed when this integration was implemented. A separate browser test with a synthetic provider passed the Google button redirect, state-cookie callback through Vite, new-user session, duplicate-email error, explicit connection and returning sign-in to the same account.

On 2 October, the real OAuth client was configured in an ignored local API environment file. After correcting the console's authorized redirect URI, a live browser check reached Google's sign-in page for Profligator, and the user confirmed successful Google OAuth sign-in. Client secrets are excluded from this documentation and repository history.
