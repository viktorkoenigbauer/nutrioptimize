# Hetzner setup: worked example

This guide separates provider configuration from application deployment. Complete
and understand each checkpoint before moving on. It complements the
[provider-neutral self-hosting guide](SELF_HOSTING.md); Hetzner is an example,
not a requirement.

## 1. Create the server

- Location: Germany or Finland, close to the user and inside the EU.
- Image: Ubuntu 24.04 LTS.
- Size: 2 GB RAM with 2 GB swap is the practical minimum for one private user.
  Four GB RAM is recommended if the price difference is acceptable because it
  leaves more room for builds, upgrades and database maintenance. Prefer x86 for
  the broadest image compatibility; the selected images also support ARM.
- Networking: public IPv4 and IPv6 for the simplest first deployment.
- Authentication: add an Ed25519 SSH public key during creation.
- Backups: enable Hetzner's daily backups before importing real data, but do not
  treat them as the only database backup.
- Label: `project=nutrioptimize`.

Why not more CPU first: PostgreSQL, Caddy and the small Python processes are not
CPU-heavy in this single-user V1. Memory and a tested backup path matter more
than additional cores until measurements show otherwise.

## 2. Add the Hetzner Cloud Firewall

Inbound rules:

- TCP 22 only from your own current public IP (or initially from anywhere if your
  IP changes often, then tighten it after testing).
- TCP 80 from anywhere, needed for HTTP-to-HTTPS redirect and certificate setup.
- TCP 443 from anywhere.

UDP 443 is intentionally not part of the default. HTTP/3 can be enabled later as
an explicit optimization; the application works over HTTPS/TCP 443.

Do not allow port 5432. The database is private. Do not allow port 8000; it is an
internal Docker port and is not published on the host.

## 3. First login and non-root admin

Connect once as root, create a normal admin user, copy the authorized SSH key,
grant sudo access, then verify a second login before disabling root/password SSH.
Keep the first session open while testing the second so a mistake does not lock
you out.

Recommended SSH policy after verification:

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

## 4. Install Docker from Docker's official repository

Follow Docker's current Ubuntu repository instructions, then install Docker
Engine, Buildx and the Compose plugin. Avoid the convenience script on a server
you intend to keep: understanding the package repository and upgrade path is part
of the exercise.

Adding an account to the `docker` group is equivalent to granting root-level
control over the host. For this learning server, using `sudo docker ...` is the
clearer security boundary.

## 5. DNS and application

Create an A record pointing your chosen API hostname to the server's IPv4 address
and an AAAA record for IPv6. DNS must resolve before Caddy can obtain a public TLS
certificate.

Clone this repository to `/srv/nutrioptimize`, create `.env` from `.env.example`,
set `PUBLIC_HOST` and `PUBLIC_ADDRESS` to the real hostname, initialize secret
files, then start the stack. Do not put the server IP, hostname or secret values
into files that will later be published.

## 6. Verification order

1. `docker compose config` parses successfully.
2. `docker compose build` succeeds.
3. Database health becomes `healthy`.
4. Migration exits successfully.
5. API liveness and readiness return success.
6. One fixture sync writes entries.
7. Authenticated REST returns the fixture day.
8. MCP Inspector lists the three read-only nutrition tools; OAuth mode also
   includes the standard read-only profile tool.
9. Caddy serves the same endpoints through HTTPS.

This order localizes failures. If step 4 fails, TLS is irrelevant; if step 7
works but step 8 fails, the database and query layer are already exonerated.

## 7. Before real data

- verify unattended security upgrades and both firewall layers;
- create an encrypted off-host PostgreSQL backup and test restoration;
- define retention for database rows, raw payloads, logs and backups;
- confirm that no password, token, IP address or real diary export is present in
  Git history;
- review the unofficial YAZIO adapter's privacy and account risks before
  enabling it.
