# Publishing source without private operational data

Reviewed on **15 November 2026**. This is the public publication procedure; actual host/account identifiers, incident evidence and private denylist values do not belong here.

## What can be public

Source, migrations, fixture-based tests, example configuration, generic setup instructions and redacted test summaries can be reviewed on GitHub. Examples should use reserved domains such as `example.com`/`example.invalid` and clearly synthetic identities. A public repository URL necessarily exposes its public namespace; it is not a private deployment origin.

Keep actual deployment hosts/IPs, operator contact emails, SMTP/OAuth/model secrets, database dumps, browser state, account screenshots, reset/verification URLs, history-rewrite backups and private runbooks outside commits. `.env` variants, artifacts, generated extension downloads and private documentation are ignored. Ignore rules do not protect a file already tracked or a forced add.

## Review before committing

```sh
git status --short
python3 scripts/check_public_privacy.py
python3 scripts/check_public_privacy.py --history
git diff --check
```

For additional known operator values, use a local JSON list or newline file stored outside tracked source:

```sh
python3 scripts/check_public_privacy.py --private-terms-file /path/to/private-terms.json
python3 scripts/check_public_privacy.py --history --private-terms-file /path/to/private-terms.json
```

The checker reports paths/categories rather than the matched value. Never put actual denylist values in command arguments, committed scanner rules or shared logs. Generic checks include common mailbox providers, cloud instance names, personal home paths, project-specific design links, private keys and selected token formats.

These commands inspect the tracked working tree or reachable Git objects. They do not automatically review staged blobs, untracked files, image content/metadata, every token format or cached remote commits. Inspect exact staged content as a separate step:

```sh
git add -- README.md docs/README.md
git diff --cached --name-only
git diff --cached --check
git diff --cached --stat
```

Review the staged patch locally without forwarding its raw output to a public issue. Check that no private file was staged and that every public file/link is intentional. When preparing small commits, count both added and deleted lines; a commit with 250 additions and 250 deletions has 500 changed lines.

## Commit identity and publication

Use the intended privacy-preserving Git author/committer identity; file-content scans alone miss commit contact metadata. Do not restore old personal metadata or original refs from a private history backup. The repository's existing rewritten history should be the base for later commits.

Check the remote tip before pushing so other contributors' work is preserved. Keep Actions disabled during this documentation publication. Inspect branch/workflow state before operations that might run automation; pushing source must not silently re-enable settings.

After pushing, verify remote branch SHA and selected file blobs. An independent fresh clone plus a history scan checks the objects GitHub advertises at that time. It does not prove that old inaccessible-looking objects, caches or external copies have been erased.

## If identifying data was already published

Removing a string from the latest README does not remove its earlier commits. Inventory all branches/tags and relevant binaries, redact/remove affected historical content, and verify an isolated rewrite before replacing remote refs. Preserve unrelated changes and use exact branch leases when rewriting. Do not casually merge old clones back into the cleaned history.

If the exposed material is a credential, revoke/rotate it privately; history editing is not revocation. A clean known-secret scan only establishes that those exact values/patterns were not found in its scope.

GitHub's [sensitive-data removal guide](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) explains the difference between rewritten refs, cached original commits and external forks/clones. Those external copies require the relevant owner/platform process. Do not claim complete erasure based only on a force push, and do not publish old private values or an operational recovery bundle while asking for help.

## Local-only documentation

Private operator write-ups are deliberately outside the public guide set. Before any publication, verify the private directory is ignored and contains no tracked paths. Keep owner-only permissions where appropriate and back it up through an approved private location. Docker build-context exclusion is separate from Git exclusion; check both.

The privacy checker is a review aid, not a substitute for careful staged inspection. Extend checks with private known values as the environment changes, while keeping the public rules generic and the output redacted.
