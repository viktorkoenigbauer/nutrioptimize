# Security policy

NutriOptimize processes health-adjacent personal data. Treat every diary record,
source credential, bearer token, OAuth token, database dump and backup as
sensitive.

## Supported version

During beta, only the newest `0.1.x` beta and the current `main` branch receive
security fixes. Older beta builds should be upgraded instead of patched in
place. Stable security-maintained releases do not exist yet.

## Reporting a vulnerability

Do not open a public issue for a suspected vulnerability. Once the GitHub
repository exists, use GitHub Private Vulnerability Reporting. Until that is
enabled, contact the repository owner through an agreed private channel.

Include the affected version, expected and observed behavior, reproduction steps
using synthetic data, and the likely impact. Do not include real nutrition data,
tokens, passwords, private keys or database dumps.

## Security baseline

The supported single-user deployment assumes:

- SSH key authentication; root and password SSH login disabled
- provider firewall and host firewall with only 22, 80 and 443 allowed as needed
- SSH restricted to the operator's current public IP where practical
- HTTPS termination through Caddy
- PostgreSQL not published to the host or internet
- API diagnostics not published to a host port and protected by the operator
  bearer token when reached through Caddy
- random secrets stored outside Git in a mode-`700` directory as mode-`440`
  files; the non-root application containers receive only the configured
  numeric secret group
- encrypted, access-controlled off-host backups
- timely operating-system, Docker and dependency updates

OAuth authenticates the private V1 data subject and the legacy bearer token
protects operator-only REST diagnostics. Neither mechanism creates a multi-user
data model. Do not expose an instance containing multiple people's data without
reviewed per-row identity, authorization and deletion boundaries.

The optional YAZIO adapter uses an email/password grant because that is what the
private mobile API exposes. Those credentials are mounted only into the sync
container as mode-restricted Docker secret files. Use a unique YAZIO password;
reusing an email-account or other important password would expand the impact of
a server compromise. The adapter never logs credentials, tokens or upstream
response bodies.

Compose file-backed secrets retain their host ownership. Set
`HOST_SECRET_GID` to the numeric output of `id -g`; do not solve container
access by making secret files world-readable.

## If a secret is exposed

1. Remove public access to the affected service if necessary.
2. Revoke or rotate the exposed credential at its source.
3. Remove the secret from the working tree and Git history; deleting only the
   latest file is insufficient.
4. Check access logs and sync history for unexpected use.
5. Restore service with a new secret and document the incident without copying
   the secret or personal data into the report.

Database-password rotation needs an explicit database role-password change; just
editing the Docker secret file does not change an already initialized PostgreSQL
role.

## Out of scope for V1

- untrusted multi-user or public-account hosting
- write-capable MCP tools
- a self-hosted identity provider
- high-availability or disaster-recovery guarantees
- a security guarantee for undocumented third-party APIs

Security controls reduce risk but do not make a self-hosted system risk-free.
