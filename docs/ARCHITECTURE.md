# Architecture decisions

## Data flow

```text
YAZIO adapter (fixture first, live later)
        |
        v
sync worker --private Docker network--> PostgreSQL
                                          ^
                                          |
Internet --> Caddy (TLS) --> API + MCP ----+
```

Only Caddy binds to the server's public ports 80 and 443. PostgreSQL and the API
have no published host ports; port 8000 exists only inside the Docker networks.
Caddy receives a separate outbound-capable network for certificate issuance;
the sync worker receives one for upstream data access. They also join the
internal backend network. PostgreSQL never joins an outbound-capable network.

The Python containers run as an unprivileged user, drop all Linux capabilities,
use a read-only root filesystem and receive only a small temporary filesystem at
`/tmp`. These controls limit accidental writes and reduce the impact of an
application compromise. They do not replace host updates or container-runtime
security.

## Why one application exposes REST and MCP

REST is useful for humans, health checks and conventional integration tests.
MCP gives NutriOptimize typed, model-callable tools. Both call the same query
service, so totals cannot silently diverge between two implementations.

## Why a separate sync process

Importing data and answering reads have different failure modes. A slow or
temporarily broken upstream should not make yesterday's stored diary unreadable.
The `sync` and `api` containers use the same image but start different commands.

## Why entries and nutrients use separate tables

A wide table with one column for every micronutrient becomes brittle. The
`nutrient_values` table allows a new nutrient code without a database migration,
while the application still enforces a canonical code and unit vocabulary.

## Idempotency

Every source item has a stable `(source, external_id)` key and a SHA-256 hash of
its canonical raw payload. A repeated sync updates the row instead of duplicating
it. Nutrients are replaced only when the hash changes.

## Calendar dates

Nutrition diaries are grouped by the user's local day. Each entry stores both an
absolute timestamp and `local_date` calculated in `Europe/Vienna`. This avoids a
late meal moving to the wrong day when data is converted to UTC.

## Authentication boundary

Local V1 can use one high-entropy bearer token. The public MCP route supports an
OAuth 2.1 resource-server mode with issuer, signature, audience, expiry, scope
and stable-subject validation. The subject allowlist matches the single-user
database boundary. This still has no tenant-owned rows or per-user deletion;
multi-user use requires authorization at every data access rather than merely
removing the allowlist.

## Raw source payloads

The raw payload is retained to make importer mistakes auditable. That improves
debuggability but increases privacy impact. It must never appear in API/MCP
responses or logs, and a later retention policy should remove it when no longer
needed.

Sync failures expose only a generic exception type in status and logs. Exception
messages from an upstream are deliberately suppressed because they can contain
request URLs, credentials or fragments of a source response.

## Missing data and deletions

Range responses include every requested calendar day and mark empty days with
`has_data: false`; an absent day is therefore not confused with a day containing
zero nutrients. Nutrient keys absent from an entry remain absent from totals.

Each source must define deletion semantics. Both current adapters return a
complete date window and mark it authoritative. Missing source entries are
therefore removed only after the full fetch and every normalization step has
succeeded; a failed or malformed response cannot trigger reconciliation.

## YAZIO boundary

The default source remains a deterministic fixture. A separate Compose overlay
enables a read-only adapter for YAZIO's undocumented private API only after the
operator deliberately supplies four source credentials. The sync container is
the only service that receives them.

The adapter is isolated in one module, validates response shapes, preserves
missing nutrients as unknown and never calls a write endpoint. It can still
break without notice because YAZIO does not publish or support the interface.
See `docs/YAZIO_UNOFFICIAL_API.md` for the maintenance and terms boundary.

The same scheduled transaction stores date-specific daily goals. Each row
keeps YAZIO's effective target and its unmodified calculation as separate value
sets. Activity energy and the preference controlling whether YAZIO consumes it
remain separate metadata; the backend does not silently add exercise calories
or relabel a YAZIO target as measured TDEE.

An authoritative diary response also enables deletion reconciliation: after a
successful fetch and upsert transaction, local source entries missing from the
same date window are deleted. A failed or malformed fetch performs no deletion.
