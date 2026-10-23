#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

fail() {
  echo "Deploy stopped: $*" >&2
  exit 1
}

command -v git >/dev/null || fail "git is not installed"

[[ -d .git ]] || fail "this directory is not a Git checkout"
[[ "$(git branch --show-current)" == "main" ]] || fail "switch to the main branch first"
[[ -z "$(git status --porcelain)" ]] || fail "the server checkout has local changes"

force_rebuild=0
if [[ "$#" -gt 1 ]]; then
  fail "usage: ./scripts/deploy.sh [--rebuild]"
fi
if [[ "$#" -eq 1 && "$1" != "--rebuild" ]]; then
  fail "usage: ./scripts/deploy.sh [--rebuild]"
fi
if [[ "${1:-}" == "--rebuild" ]]; then
  force_rebuild=1
fi

git fetch --prune origin main
current_revision="$(git rev-parse HEAD)"
target_revision="$(git rev-parse origin/main)"

if [[ "$current_revision" == "$target_revision" && "$force_rebuild" -eq 0 ]]; then
  echo "Already up to date at ${current_revision:0:12}."
  exit 0
fi

command -v docker >/dev/null || fail "docker is not installed"

# Docker group membership is equivalent to root access. On hosts where the
# operator deliberately stayed out of that group, ask sudo once for this deploy.
docker_command=(docker)
if ! docker info >/dev/null 2>&1; then
  command -v sudo >/dev/null || fail "Docker requires privileges and sudo is unavailable"
  sudo -v
  docker_command=(sudo docker)
fi

compose_files=(-f compose.yaml)
if [[ -s secrets/yazio_email.txt ]]; then
  compose_files+=(-f compose.yazio.yaml)
fi

compose() {
  "${docker_command[@]}" compose "${compose_files[@]}" "$@"
}

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_path=""

# A logical dump is taken before code or migrations change. The directory is
# ignored by Git, but the operator still needs an encrypted off-server backup.
if [[ -n "$(compose ps --quiet db 2>/dev/null)" ]]; then
  mkdir -p backups
  backup_tmp="$(mktemp "backups/.pre-deploy-${timestamp}.XXXXXX")"
  # These variables are intentionally expanded inside the database container.
  # shellcheck disable=SC2016
  if ! compose exec -T db sh -ec \
    'export PGPASSWORD="$(cat "$POSTGRES_PASSWORD_FILE")"; exec pg_dump --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --format=custom --no-owner --no-acl' \
    > "$backup_tmp"; then
    rm -f "$backup_tmp"
    fail "database backup failed"
  fi
  backup_path="backups/pre-deploy-${timestamp}-${current_revision:0:12}.dump"
  chmod 600 "$backup_tmp"
  mv "$backup_tmp" "$backup_path"
  echo "Database backup: $backup_path"
fi

on_error() {
  echo >&2
  echo "Deploy failed. Previous code revision: $current_revision" >&2
  if [[ -n "$backup_path" ]]; then
    echo "Pre-deploy database backup: $backup_path" >&2
  fi
  echo "No automatic rollback was attempted because a migration may have run." >&2
}
trap on_error ERR

if [[ "$current_revision" != "$target_revision" ]]; then
  git merge --ff-only "$target_revision"
fi
compose config >/dev/null
compose up --detach --build --remove-orphans

ready=0
for _attempt in {1..30}; do
  if compose exec -T api python -c \
    "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=2)" \
    >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done

[[ "$ready" -eq 1 ]] || fail "the API did not become ready within 60 seconds"

trap - ERR
compose ps
echo
if [[ "$current_revision" == "$target_revision" ]]; then
  echo "Rebuild complete at ${target_revision:0:12}"
else
  echo "Deploy complete: ${current_revision:0:12} -> ${target_revision:0:12}"
fi
