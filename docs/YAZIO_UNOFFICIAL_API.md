# Unofficial YAZIO adapter

## Status and boundary

YAZIO does not publish, endorse or support the API used by this adapter. The
interface was reverse-engineered from app traffic by an independent community.
It can change or disappear without notice, and using it remains subject to
YAZIO's current terms. NutriOptimize is not affiliated with YAZIO GmbH.

The adapter is deliberately read-only. It requests diary entries, referenced
products and referenced recipes. It does not create, edit or delete anything in
the YAZIO account.

Primary community references:

- [API specification](https://github.com/yazio-community/yazio-api-specification)
- [Generated Python SDK](https://github.com/yazio-community/yazio-sdk-python)
- [Exporter used to cross-check nutrient scaling](https://github.com/Vinche59/yazio-exporter)

The implementation calls the small required endpoint set directly instead of
embedding the generated SDK. That keeps the authentication, response checks and
normalization visible in `app/sources/yazio.py`.

## Why this is an optional Compose overlay

The normal `compose.yaml` uses synthetic data and needs no YAZIO credentials.
The additional `compose.yazio.yaml` mounts four extra Docker secrets only into
the sync container. The API, Caddy, migration and database containers never
receive those credentials.

The password grant used by the private API means a YAZIO email/password login
must be available. Accounts that only use an Apple or Google sign-in may need a
separate YAZIO password before this path can work. Never paste credentials into
an issue, documentation, a shell command or this chat.

Create the files interactively:

```sh
sh scripts/init-yazio-secrets.sh
```

The script keeps the directory at mode `700` and its files at mode `440`.
Set `HOST_SECRET_GID` in `.env` to the numeric output of `id -g`; the
non-root sync container receives that group instead of requiring
world-readable files.

To correct or rotate only the account email and password without touching the
app-level client values, run:

```sh
sh scripts/update-yazio-account-secrets.sh
```

The community specification documents the app-level client id and client
secret. They identify the mobile application rather than the individual user,
but NutriOptimize still keeps them out of the repository. Obtain the current
values and accepted `User-Agent` from the specification linked above.

## Safe first live run

Stop the scheduled fixture worker, validate the merged configuration and build:

```sh
sudo docker compose stop sync
sudo docker compose -f compose.yaml -f compose.yazio.yaml config
sudo docker compose -f compose.yaml -f compose.yazio.yaml build sync
```

Run one foreground import before enabling the scheduler:

```sh
sudo docker compose -f compose.yaml -f compose.yazio.yaml \
  run --rm sync python -m app.sync_once
```

Then inspect the generic sync status and a known day through the authenticated
API or MCP. The adapter never prints credentials or upstream response bodies.
Only after the results match YAZIO should the regular worker be started:

```sh
sudo docker compose -f compose.yaml -f compose.yazio.yaml up -d sync
```

Always use both Compose files for later YAZIO worker operations. Running only
`compose.yaml` switches that newly created worker back to the fixture source.

## Data interpretation

- Product nutrients are reported per one base unit and are multiplied by the
  consumed amount.
- Recipe nutrients are reported per portion and are multiplied by the logged
  portion count.
- Quick-entry nutrients are already totals and are not scaled again.
- Missing nutrient keys remain unknown; they are not converted to zero.
- Upstream timestamps without an offset are interpreted in `APP_TIMEZONE`.
- A completed day response is treated as authoritative. Entries removed in
  YAZIO are removed locally during the next sync of that date window.
- The daily-summary widget supplies YAZIO's effective calorie and macronutrient
  targets plus activity-energy metadata. The unmodified-goals endpoint supplies
  YAZIO's calculation before manual overrides. Both variants are stored per
  local date and returned as `targets`; neither is described as measured TDEE.
- Only normalized target fields are retained from the widget response. Embedded
  profile fields are deliberately not copied into the target table.

## Expected breakage modes

The v22 API checks the mobile app version embedded in `User-Agent`. A rejected
version appears locally as `YazioClientVersionBlocked`; update the configured
value only after checking the current community specification. Authentication
failures appear as `YazioAuthenticationError`. Other non-success responses are
reduced to their status code so private response data cannot enter logs.

Keep `SYNC_LOOKBACK_DAYS` large enough to cover entries that you commonly edit
after the fact. Historical changes older than that window require a deliberate
one-shot backfill with a larger lookback (maximum 90 days per run).
