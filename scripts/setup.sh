#!/usr/bin/env sh
set -eu

if [ ! -t 0 ]; then
  echo "Run this setup assistant in an interactive terminal." >&2
  exit 1
fi

root_dir=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root_dir"

if [ -e .env ]; then
  echo "Refusing to overwrite the existing .env file." >&2
  echo "Edit it manually or move it aside before running first-time setup." >&2
  exit 1
fi

created_env=0
setup_complete=0

cleanup() {
  if [ "$created_env" -eq 1 ] && [ "$setup_complete" -eq 0 ]; then
    rm -f .env
    echo "Setup did not finish; the newly created .env file was removed." >&2
  fi
}

trap cleanup EXIT
trap 'exit 130' HUP INT TERM

command -v python3 >/dev/null 2>&1 || {
  echo "python3 is required to generate secure local secrets." >&2
  exit 1
}

cp .env.example .env
chmod 600 .env
created_env=1

set_env() {
  env_key=$1
  env_value=$2
  env_tmp=$(mktemp ./.env.setup.XXXXXX)
  awk -v key="$env_key" -v value="$env_value" '
    BEGIN { found = 0 }
    index($0, key "=") == 1 {
      print key "=" value
      found = 1
      next
    }
    { print }
    END {
      if (!found) print key "=" value
    }
  ' .env > "$env_tmp"
  chmod 600 "$env_tmp"
  mv "$env_tmp" .env
}

ask() {
  prompt=$1
  default_value=$2
  printf "%s [%s]: " "$prompt" "$default_value"
  IFS= read -r answer
  if [ -z "$answer" ]; then
    answer=$default_value
  fi
}

printf "\nNutriOptimize first-time setup\n"
printf "This creates local configuration and secret files. Nothing is uploaded.\n\n"

ask "Public hostname without https:// (use localhost for a local test)" "localhost"
public_host=$answer
case "$public_host" in
  *://*|*/*|*" "*)
    echo "Use a hostname only, for example nutrition.example.com." >&2
    exit 1
    ;;
esac

if [ "$public_host" = "localhost" ]; then
  public_address="http://localhost"
else
  public_address="https://$public_host"
fi

ask "Application timezone" "Europe/Vienna"
app_timezone=$answer

host_secret_gid=$(id -g)
set_env PUBLIC_HOST "$public_host"
set_env PUBLIC_ADDRESS "$public_address"
set_env APP_TIMEZONE "$app_timezone"
set_env HOST_SECRET_GID "$host_secret_gid"

sh scripts/init-secrets.sh

printf "\nConfigure the unofficial YAZIO adapter now? [y/N]: "
IFS= read -r configure_yazio
case "$configure_yazio" in
  y|Y|yes|YES)
    printf "Current YAZIO User-Agent from the community specification: "
    IFS= read -r yazio_user_agent
    if [ -z "$yazio_user_agent" ]; then
      echo "The YAZIO User-Agent is required for live synchronization." >&2
      exit 1
    fi
    yazio_secret_count=0
    for secret_file in \
      secrets/yazio_email.txt \
      secrets/yazio_password.txt \
      secrets/yazio_client_id.txt \
      secrets/yazio_client_secret.txt
    do
      if [ -s "$secret_file" ]; then
        yazio_secret_count=$((yazio_secret_count + 1))
      fi
    done
    case "$yazio_secret_count" in
      0)
        sh scripts/init-yazio-secrets.sh
        ;;
      4)
        printf "Reusing the complete existing YAZIO secret set.\n"
        ;;
      *)
        echo "YAZIO secrets are incomplete; fix or remove that set before retrying." >&2
        exit 1
        ;;
    esac
    set_env YAZIO_USER_AGENT "$yazio_user_agent"
    ;;
  *)
    configure_yazio="no"
    ;;
esac

setup_complete=1
trap - EXIT HUP INT TERM

printf "\nSetup files are ready.\n"
printf "Review .env before starting the stack. Configure OAuth only after the\n"
printf "fixture test works; docs/OAUTH_SETUP.md lists every required field.\n\n"

if [ "$configure_yazio" = "no" ]; then
  printf "Start the test stack with:\n"
  printf "  sudo docker compose up --build -d db migrate api caddy\n"
  printf "  sudo docker compose run --rm sync python -m app.sync_once\n"
else
  printf "Start with fixture data first. After it succeeds, run the live import with:\n"
  printf "  sudo docker compose -f compose.yaml -f compose.yazio.yaml run --rm sync python -m app.sync_once\n"
fi
