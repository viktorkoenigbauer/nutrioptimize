# Contributing

NutriOptimize favors understandable, reviewable changes over clever shortcuts.
Contributions should preserve the single-user security and privacy boundaries or
clearly explain why those boundaries must change.

## Development rules

1. Use only synthetic data in code, tests, issues and documentation.
2. Never commit `.env`, files under `secrets/`, private keys, logs, database dumps
   or server-specific addresses.
3. Add or update tests for changed behavior.
4. Add a migration for every database-schema change; do not mutate an existing
   released migration.
5. Keep REST and MCP queries on the same service layer so their results agree.
6. Document new public ports, outbound connections, stored fields and third-party
   dependencies.

## Comments and documentation

Comments should explain **why** a decision exists: a privacy boundary, a security
tradeoff, a surprising nutrition rule or an external-system constraint. Avoid
comments that merely translate the next line into English.

Public functions with non-obvious inputs or semantics should have a short
docstring. User-facing setup instructions should include the purpose of each
step, a verification check and a safe rollback or recovery note where relevant.

## Source adapters

A source adapter must normalize data through the domain layer and must not log
credentials or raw responses. Its documentation must state:

- how authorization works and where secrets are stored;
- which external host receives data;
- whether the interface is official and supported;
- rate-limit, deletion and reconciliation behavior;
- which personal fields are retained.

Do not add a real account export as a test fixture.

## Before proposing a change

Install the pinned development tools from `requirements-dev.txt`, then run:

```sh
ruff check app migrations scripts/check_mcp.py tests
ruff format --check app migrations scripts/check_mcp.py tests
pip-audit --requirement requirements.txt --progress-spinner off
docker compose config
```

Run the unit tests as documented in the CI workflow. For deployment changes,
also build the images and exercise liveness, readiness, one fixture sync,
authenticated REST and MCP tool discovery.
