#!/usr/bin/env sh
set -eu

umask 077
mkdir -p secrets
chmod 700 secrets

if [ ! -s secrets/postgres_password.txt ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > secrets/postgres_password.txt
fi

if [ ! -s secrets/api_bearer_token.txt ]; then
  python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > secrets/api_bearer_token.txt
fi

chmod 440 secrets/postgres_password.txt secrets/api_bearer_token.txt

echo "Secret files are ready in ./secrets with mode 440 (their contents are intentionally not printed)."
echo "Container secret group: $(id -g). Set HOST_SECRET_GID to this value when it is not 1000."
