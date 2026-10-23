# Privacy and data lifecycle

NutriOptimize is self-hosted. The person or organization operating an instance
decides why data is processed, who can access it, how long it is kept and where
backups are stored. This document describes the software, not legal advice.

## Data processed

Depending on the configured source, the database may contain meal names,
timestamps, food names, quantities, nutrient values, source identifiers and the
original imported payload. Together these can reveal habits and health-related
information even when they are not a medical record.

The system also stores sync metadata such as time range, status and item counts.
Failure records intentionally contain only a generic exception type, because an
upstream error message could contain credentials, URLs or diary fragments.

## Where data goes

By default:

- diary data is stored in the local PostgreSQL Docker volume;
- REST and MCP return selected structured data only after authentication; the
  public MCP route can require OAuth while private REST diagnostics retain the
  operator bearer token;
- raw source payloads are not returned by REST or MCP;
- PostgreSQL is not exposed to the host network;
- application telemetry and analytics are not sent by this repository.

Infrastructure still communicates externally when required: Caddy contacts a
certificate authority for TLS, the host contacts package and container registries
for updates, and the optional live adapter contacts `yzapi.yazio.com`. Enabling
that adapter sends the configured account credentials to YAZIO's token endpoint
and reads diary, product and recipe data into the self-hosted database.

## Logs

Logs are operational data and can still reveal timestamps, IP addresses and
request patterns. The Compose configuration rotates local container logs. Do not
log bearer tokens, OAuth access or refresh tokens, source credentials, request
bodies or raw diary payloads.
Restrict log access and define an appropriate retention period.

Routine synchronization suppresses HTTP-client request URLs because product and
recipe identifiers can reveal health-adjacent information when correlated with
an upstream catalogue. Logs retain aggregate item counts and redacted error
classes.

## Retention and deletion

V1 does not yet implement automatic diary retention or a self-service deletion
workflow. PostgreSQL data, Docker volumes and every backup must be included in a
deletion plan before real data is used. Raw payload retention improves importer
debugging but increases privacy impact; operators should keep it only as long as
needed.

Deleting the live database does not delete off-host backups. Backup expiry and
secure destruction are separate operator responsibilities.

## Backups

Backups contain the same sensitive data as the live database. Encrypt them,
restrict access, keep at least one copy off the server, test restoration and set
an expiry schedule. A cloud-server snapshot is useful but is not by itself a
tested PostgreSQL backup.

## Safe public development

Only deterministic synthetic fixtures belong in the public repository, tests,
issues, pull requests and screenshots. Before publishing, inspect Git history as
well as the current files for real diary exports, hostnames, IP addresses,
credentials, database dumps and logs.
