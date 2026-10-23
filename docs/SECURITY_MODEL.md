# Security model

This document makes the V1 trust boundaries explicit. It is a design aid, not a
claim that the system is invulnerable.

## Assets

- nutrition diary entries and raw imported payloads
- API bearer token and source credentials
- PostgreSQL password and database backups
- SSH private key and server administrator access
- integrity of nutrition totals returned to NutriOptimize

## Trust boundaries

```text
untrusted internet
      |
      v
provider firewall -> host firewall -> Caddy/TLS -> OAuth for MCP
                                                    bearer token for private REST
                                                        |
                                                        v
                                                 API/MCP + database

trusted operator -> SSH key -> hardened host -> Docker administration
```

The host administrator and anyone with Docker access are fully trusted: Docker
control is effectively root access. The legacy bearer token grants read access
to the private REST diagnostics. Remote MCP clients use short-lived OAuth access
tokens. Because this database contains one person's diary, the server also
requires an explicit stable-subject allowlist. The language model is not trusted
to modify data, so V1 publishes read-only MCP tools.

## Main threats and controls

| Threat | V1 control | Remaining risk |
|---|---|---|
| Internet scanning | provider and host firewalls | a public web service is still reachable |
| Traffic interception | automatic HTTPS through Caddy | compromised DNS, CA or client remains possible |
| Stolen OAuth token | short expiry; signature, issuer, audience, scope and subject checks | valid tokens remain usable until expiry or revocation takes effect |
| Wrong OAuth tenant user | immutable `sub` allowlist | the operator must update the allowlist deliberately after identity changes |
| Database exposure | no published PostgreSQL port; private Docker network | host or Docker compromise bypasses this boundary |
| Bearer-token exposure | mounted only into the API container | host or Docker administrators can still read the secret |
| Malicious MCP action | only read-only tools | returned personal data can still be disclosed by an authorized client |
| Secret leakage in errors | generic stored and logged sync errors | a new adapter can reintroduce unsafe logging |
| Container breakout impact | non-root Python image, read-only root filesystem, no capabilities | kernel and container-runtime vulnerabilities remain |
| Disk exhaustion | rotated container logs | database and backup growth still need monitoring |
| Data loss | documented off-host backup requirement | backups must be implemented and restoration tested by the operator |
| Supply-chain compromise | pinned direct Python versions, image digests and reviewed CI action revisions | transitive packages and future updates still require review |

## Network policy

Only TCP 80 and 443 are public for the application. SSH TCP 22 should be limited
to an operator IP. TCP 5432 and 8000 must not be public. The sync worker alone
gets an outbound-capable application network; PostgreSQL stays on an internal
network. Caddy needs outbound access for certificate management.

## Authentication boundary

The public MCP endpoint supports OAuth 2.1 authorization-code flows with PKCE
through an external identity provider. NutriOptimize is only the resource server:
it does not store login passwords or issue tokens. It validates the JWT signature,
issuer, audience, expiry, read scope and stable subject on every MCP request.

This remains a single-user data model. Removing the subject allowlist does not
turn it into a multi-user service; real multi-user support requires tenant-owned
rows, authorization on every query, deletion/export workflows and isolation
tests. TLS alone does not provide authorization.

## Privacy limitation

The database retains original imported payloads for auditability. This helps
debug importer changes but increases the consequences of database or backup
disclosure. Automatic retention and deletion are required before the design can
claim mature privacy lifecycle management.
