# Password recovery

The existing login **Forgot password?** link now opens `/forgot-password`. Request a link using the account email, open the message, enter and confirm a new password, then sign in normally. The forms reuse the original login palette and assets.

## Gmail configuration

Use a Google **app password**, created after signing in at [Google App Passwords](https://myaccount.google.com/apppasswords). Google requires 2-Step Verification; the option may be unavailable for some managed or Advanced Protection accounts. A normal Google account password is not the SMTP credential for this integration. See [Google's app password instructions](https://support.google.com/accounts/answer/185833).

Fill these in `apps/api/.env` locally:

```dotenv
PROFLIGATOR_PASSWORD_RESET_EMAIL_BACKEND=smtp
PROFLIGATOR_SMTP_HOST=smtp.gmail.com
PROFLIGATOR_SMTP_PORT=587
PROFLIGATOR_SMTP_SECURITY=starttls
PROFLIGATOR_SMTP_USERNAME=support@example.com
PROFLIGATOR_SMTP_PASSWORD=your-google-app-password
PROFLIGATOR_SMTP_FROM_EMAIL=support@example.com
```

The sender and SMTP username should be the same Gmail address. Keep credentials in the backend environment. The Gmail fields have been prepared locally, with delivery disabled until credentials are supplied. Restart the API after changing its environment. For containers, use the same settings in `infra/.env.production`; Compose passes them to the backend. Keep the public web URL on HTTPS in production.

Run database migrations before starting an existing deployment:

```sh
apps/api/.venv/bin/alembic -c apps/api/alembic.ini upgrade head
```

The local SQLite database was backed up under ignored `artifacts/database-backups` before adding the recovery migration. No passwords were changed during implementation.

## Behavior and safeguards

Links expire after 15 minutes by default. Tokens contain 48 cryptographically random bytes; only their SHA-256 hashes are stored. The email link uses a fragment, which the reset screen removes after reading it. Tokens are consumed atomically and cannot be reused; resetting also invalidates other outstanding links for that account.

Recovery returns the same accepted response for unknown accounts and throttled addresses. Database counters allow three requests per email and thirty per directly observed client IP per hour. SMTP delivery and account lookup occur after the response. Configure proxy trust and ingress limits for the chosen host; these checks do not establish production traffic handling.

A reset increments the account's authentication version and revokes refresh/extension sessions and pending Google linking attempts. Access tokens and stale refreshes from before the reset are rejected. Password policy matches registration (10–128 characters), requires confirmation and uses the existing Argon2 hash. The user receives a change notification and signs in again. A Google-only account can set a password by proving access to its registered email through this flow; its Google identity remains connected.

The implementation follows [OWASP's password recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html). Email delivery failures log the exception type without credentials, addresses or reset links. Background email tasks are not a durable mail queue; delivery retry/monitoring on a public host remains deployment work.

## Verification

```sh
apps/api/.venv/bin/python -m pytest -q apps/api/tests/test_password_recovery.py
apps/api/.venv/bin/python scripts/verify_password_recovery.py --output-dir artifacts/recovery
```

The browser runner creates isolated API/web servers and a loopback SMTP server. It exercises the real request/reset screens, receives actual SMTP messages, verifies password confirmation, old/new password behavior, one-use links, change notifications, and mobile layout. It sends no external email and never touches real accounts. CI includes this runner.

The backend suite passed 184 tests, with an additional empty-SMTP-configuration regression passing afterward (185 covered tests in total). The browser/SMTP acceptance also passed on 7 October. Gmail authentication and live delivery are still pending the sender's app password.

## Live reset-mail check — 13 October 2026

The reset sender configured reset address is stored in the ignored backend `.env`, with owner-only permissions. Gmail authentication passed over verified STARTTLS. The actual forgot-password route returned HTTP 202 for the authorized existing account, and Gmail accepted its reset message. Mailbox receipt and completion of the reset have not been confirmed; the test did not change the account password. The emailed link points to `http://localhost:5173` and expires after 15 minutes. The local API health endpoint and forgot-password page returned HTTP 200.

The existing SQLite database was backed up before applying the pending migrations through `20261013_0012`. Delivery evidence is retained privately; no actual sender identity is included in the public repository.

The separate verification sender remains disabled while the user resolves Google's identity-verification block for that account. Google's [sensitive-action guidance](https://support.google.com/accounts/answer/7162782) describes verification methods and possible seven-day restrictions; the screenshot alone does not establish the specific cause.
