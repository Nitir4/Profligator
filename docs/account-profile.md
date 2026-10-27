# Edit your Profligator profile

Open the account menu and choose **Edit profile**, or visit `/settings/account#profile`.

- **Display name:** up to 80 characters. Leave it blank to show your username instead.
- **Username:** 3–64 letters, numbers, dots, underscores or hyphens. Names are unique regardless of letter case, so `Alex.Dev` and `alex.dev` cannot belong to different accounts.
- **Short bio:** up to 280 characters.
- **Profile photo:** JPEG, PNG or WebP still image, up to 4 MiB and 16 megapixels.

Choose **Save profile** to save the text fields. Uploading or removing a photo saves immediately and keeps any unsaved text in the form. Photos are centered, cropped to 384 × 384 pixels, corrected for orientation and re-encoded as JPEG without source metadata. Initials appear when no photo is set.

The header, dashboard and active shared profile show these details. Account email, Google connection, login sessions, extension connections, linked coding-platform handles, history and existing share links remain attached to the same account ID. Changing your account username does not rename a coding-platform profile.

## Storage and access

Migration `20261027_0013` adds display name, bio and photo revision fields to `users`, a case-insensitive unique username index, and a separate `user_avatars` table. Processed photos are included in normal database backups and survive container replacement. Raw uploads and metadata are not stored.

The API updates only the authenticated account and rejects extra fields such as email, role or user ID. A database unique index handles competing username claims. Images are decoded and validated in a worker thread with bounded file/pixel limits; animated and unsupported formats are rejected.

| Endpoint | Access and behavior |
| --- | --- |
| `PUT /api/v1/account/profile` | Save the authenticated user's `handle`, `display_name` and `bio` |
| `PUT /api/v1/account/avatar` | Save a validated raw image upload |
| `GET /api/v1/account/avatar` | Read the authenticated user's processed photo |
| `DELETE /api/v1/account/avatar` | Remove the authenticated user's photo |
| `GET /api/v1/public-profiles/{token}/avatar` | Read a photo only through an active shared-profile token |

Shared responses include the chosen profile details, not the account email. Photo responses use private/no-store cache headers. Removing the photo or revoking sharing blocks subsequent shared-photo reads; a previously downloaded copy cannot be recalled.

## Implementation and checks

`ProfileEditor.tsx` sends updates through `api.ts`; `AccountPage.tsx` applies the response to its current account state. `ProfileAvatar.tsx` renders a photo or initials in the editor, workspace header, dashboard and shared page. Content-driven header height and wrapping accommodate longer names and bios.

`account_profile.py` validates updates and normalizes images with Pillow. `report_routes.py` checks sharing consent before returning public identity details or photo bytes. Account relationships continue to use the immutable user ID, while existing share URLs keep their random token.

API tests in `apps/api/tests/test_account_profile.py` cover validation, case-insensitive conflicts, session/history preservation, image formats/metadata, ownership isolation and photo removal/revocation. Run them from the repository root:

```sh
uv run --project apps/api --dev pytest -c apps/api/pyproject.toml apps/api/tests/test_account_profile.py
uv run --project apps/api --dev python scripts/verify_editable_profile.py
```

The browser script checks real local UI/API behavior using an isolated database. Its optional `--base-url` mode creates disposable accounts on the target site and records their exact IDs for operator cleanup; use it only for an authorized hosted acceptance run. The 27 October release passed local and live HTTPS checks for text persistence, photo upload/removal, sharing, long names and mobile layout.
