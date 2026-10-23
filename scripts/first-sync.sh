#!/usr/bin/env sh
set -eu

docker compose run --rm sync python -m app.sync_once
