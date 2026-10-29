# Project documentation

Reviewed against the repository on **15 November 2026**. Use the current guides below for implemented behavior. Older dated audits retain their original measurements; they are not new test results or a current production-health claim.

## Start here

| Need | Guide |
| --- | --- |
| Install dependencies and run locally | [Project README](../README.md#run-locally), [API setup](../apps/api/README.md) |
| Understand supported platforms and data gaps | [Public collectors](public-collectors.md), [collection flow](profile-collection-structure.md) |
| Edit account identity and photos | [Account profile](account-profile.md) |
| Distinguish sign-in, inbox proof and coding-profile proof | [Account security](account-security.md), [Google sign-in](google-sign-in.md) |
| Configure or test password recovery | [Password recovery](password-recovery.md) |
| Install/connect the browser extension | [Browser extension](browser-extension.md) |
| Understand records, clustering and matching | [Backend design](backend-design.md), [Groq matching](groq-matching.md) |
| Choose and run verification | [Testing and evidence](testing.md) |
| Review generic container prerequisites | [Deployment](deployment.md) |
| Publish source without operational/private data | [Publication privacy](publication-privacy.md) |
| Decide what still needs acceptance | [Remaining work](remaining-work.md) |

## How to interpret the guides

Implemented means the behavior exists in source. A deterministic test checks it against fixtures or a simulated provider. A live check establishes only the account, provider response and conditions observed at its recorded date. Representative acceptance requires broader evidence; the presence of a model adapter or a public collector is not proof of accuracy or complete history.

The web application, API, extension and public sharing pages consume the same persisted coding records. Account identity is separate from a linked provider handle. Provider calendars, imported solves and confirmed unique clusters measure different things.

The report diagrams under `report-diagrams/` explain the original model. The [backend mapping](backend-design.md) documents implementation differences and later migrations. The [scope review](project-scope-review.md), [classification audit](classification-audit.md) and [duplicate audit](duplicate-audit.md) are dated design/evaluation records, not current completion percentages.

## Documentation boundaries

Public guides use reserved example domains, synthetic mailboxes and generic configuration names. Actual hosts, sender identities, secrets, account histories, browser state, backup locations and operational incident evidence stay outside public commits. Private local operator notes are excluded from Git and the Docker build context; they are not part of this public documentation set.

The documentation refresh was performed on 15 November. Any earlier dates assigned to its Git commits for requested history spacing describe commit metadata, not separate execution or verification dates. Check [testing](testing.md) for what was actually rerun.
