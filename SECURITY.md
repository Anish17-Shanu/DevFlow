# Security Policy

## Supported versions

| Version | Supported |
| --- | --- |
| 2.x | Yes |
| 1.x | No |

## Reporting a vulnerability

Report vulnerabilities privately through GitHub Security Advisories:
<https://github.com/Anish17-Shanu/DevFlow/security/advisories/new>

Do not open a public issue for a suspected vulnerability. Include:

- affected version or commit,
- reproduction steps or a proof of concept,
- impact assessment (data exposure, privilege escalation, denial of service),
- any suggested fix.

You can expect an acknowledgement within 3 business days and a status update within
10 business days. Once a fix ships, the advisory is published with credit unless you
prefer to stay anonymous.

## Scope

In scope: authentication and authorization bypass, cross-tenant data access, secret
disclosure, remote code execution through task configuration, SSRF through HTTP task
handlers, queue or execution state corruption, and denial of service against the API.

Out of scope: findings that require a compromised host or database, social engineering,
and reports produced solely by automated scanners without a demonstrated impact path.

## Security controls in this repository

- API keys are hashed with SHA-256; only prefixes are stored for display.
- Every API route and WebSocket subscription is authenticated and tenant-scoped.
- Roles: `viewer`, `operator`, `admin`; admin-only routes cover keys, secrets, webhooks and archiving.
- Request bodies are capped at 1 MiB by default; rate limits are per key.
- Secrets are encrypted at rest with Fernet and never returned in plaintext.
- Webhook payloads are signed with HMAC-SHA256.
- HTTP task handlers block private network targets unless explicitly enabled.
- Containers run as non-root with `no-new-privileges`, dropped capabilities and read-only root filesystems (Kubernetes).
- CI scans images with Trivy and blocks high/critical vulnerabilities; a CycloneDX/SPDX SBOM is produced per build.

## Patch SLA

| Severity | Target |
| --- | --- |
| Critical | Remediate within 7 days; block releases immediately |
| High | Remediate within 14 days |
| Medium | Next scheduled release |
| Low | Backlog |

Dependency update pull requests are opened automatically by Dependabot. A high or
critical advisory that cannot be patched immediately must be documented in the release
notes with a mitigation.

## Secrets

Never commit `.env` files, API keys, database passwords, or encryption keys. Production
deployments inject secrets through a secret manager (for example External Secrets,
Sealed Secrets, or the cloud provider's secret store) and rotate the bootstrap key after
issuing scoped keys.
