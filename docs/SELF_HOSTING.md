# Self-hosting guide

This guide is provider-neutral. The Hetzner document gives one concrete example,
but the same boundaries apply to a home server, another cloud provider or a
local VM.

## 1. Choose where it runs

| Option | Advantages | Responsibilities |
|---|---|---|
| Home server | physical control, no monthly VM fee | power, uptime, router/NAT, secure remote access, off-site backup |
| EU cloud VM | easy public IP, predictable uptime, simple DNS | provider trust, monthly cost, account security, data-region choice |
| Local-only computer | smallest exposure | MCP is unavailable when the computer sleeps; remote access is harder |

For one private user, 2 GB RAM plus 2 GB swap is a practical minimum for this
stack. Four GB RAM is the more comfortable recommendation for builds, upgrades
and database maintenance. Start small, measure, and resize only when necessary.

Use a supported LTS operating system, currently Ubuntu 24.04 LTS in the tested
example. Prefer a server in a legally and geographically appropriate region.

## 2. Establish the host boundary

Before deploying the application:

1. Add an Ed25519 SSH public key during server creation.
2. Create a normal administrator with `sudo`.
3. Test a second key-based login before closing the first session.
4. Disable root SSH login and password authentication.
5. Enable automatic security updates.
6. Configure both provider and host firewalls.

Required inbound rules:

| Port | Source | Purpose |
|---|---|---|
| TCP 22 | operator IP only where possible | SSH administration |
| TCP 80 | anywhere | redirect and certificate setup |
| TCP 443 | anywhere | HTTPS API and MCP |

Do not expose PostgreSQL 5432 or the API's internal container port 8000. Neither
is published by the default Compose configuration. No public UDP port is
required.

## 3. Install the runtime

Install Docker Engine, Buildx and the Compose plugin from Docker's official
repository. Review the repository and package-signing instructions instead of
piping a convenience script into a shell.

Membership in the `docker` group is effectively root access. The learning setup
uses `sudo docker ...` to keep that privilege boundary visible.

## 4. Prepare configuration and secrets

Obtain the repository, enter its directory and run the guided first-time setup:

```sh
./scripts/setup.sh
```

The assistant creates `.env`, records the host's numeric group and generates
permission-restricted secret files. The application containers stay
unprivileged and receive only this supplementary group so they can read the
mode-`440` file-backed secrets. It refuses to replace an existing `.env`.

For a public hostname, set these non-secret values in `.env`:

```text
PUBLIC_HOST=nutrition.example.com
PUBLIC_ADDRESS=https://nutrition.example.com
```

Create matching DNS A and, if used, AAAA records before starting Caddy. Secret
files stay under `secrets/`, are mode-restricted and ignored by Git. Back them up
only through an encrypted secret-management process.

For a remote AI-client connection, complete [OAuth setup](OAUTH_SETUP.md) before
changing `MCP_AUTH_MODE` from `static` to `oauth`. OAuth settings are public
identifiers, but tokens and provider client secrets remain confidential.

## 5. Validate before starting

```sh
docker compose config
docker compose build
docker compose up -d db migrate api caddy
docker compose ps
```

Then perform one synthetic import:

```sh
docker compose run --rm sync python -m app.sync_once
```

Verify in this order:

1. database health is `healthy`;
2. migration completed successfully;
3. `/health/live` and `/health/ready` succeed;
4. an unauthenticated `/v1/...` request is rejected;
5. an authenticated fixture request returns synthetic data;
6. MCP exposes exactly the documented read-only tools; OAuth mode also exposes
   the read-only `get_profile` identity tool;
7. the public hostname serves a valid HTTPS certificate.

This sequence makes failures easier to locate. Do not connect a real nutrition
source until the fixture path works and the backup plan is tested.

## 6. Start regular synchronization

```sh
docker compose up -d sync
```

The default source remains the synthetic fixture. The optional YAZIO adapter is
enabled with the separate Compose overlay only after its local secret files
exist. It uses an unsupported private API, so review its account, privacy and
maintenance tradeoffs before enabling it.

## 7. Back up and restore

Use a PostgreSQL-aware dump, encrypt it and move it off the server. Also retain
the configuration needed to rebuild the host, but never commit secrets. Define:

- backup frequency and retention;
- encryption and key recovery;
- off-host destination and access policy;
- a restore test schedule;
- deletion of expired backups.

A provider snapshot helps recover a whole VM but is not a substitute for a
tested logical database restore. Write and test the exact backup commands for the
chosen environment before importing real data.

## 8. Update safely

Use the reviewed Git workflow and server-side script described in
[Deploying updates](DEPLOYMENT.md). It takes a logical database dump before
pulling the main branch, rebuilds the stack and checks readiness.

Never assume that changing a secret file rotates the credential inside an
already initialized external system. Database, source and API tokens each need a
documented rotation procedure.
