#!/bin/sh
set -eu

if [ ! -t 0 ]; then
  echo "Run this script in an interactive terminal." >&2
  exit 1
fi

secret_dir="secrets"
email_file="$secret_dir/yazio_email.txt"
password_file="$secret_dir/yazio_password.txt"
client_id_file="$secret_dir/yazio_client_id.txt"
client_secret_file="$secret_dir/yazio_client_secret.txt"
email_tmp=""
password_tmp=""
terminal_hidden=0

restore_terminal() {
  if [ "$terminal_hidden" -eq 1 ]; then
    stty echo
    terminal_hidden=0
    printf "\n"
  fi
}

cleanup() {
  restore_terminal
  if [ -n "$email_tmp" ]; then
    rm -f "$email_tmp"
  fi
  if [ -n "$password_tmp" ]; then
    rm -f "$password_tmp"
  fi
}

trap cleanup EXIT
trap 'cleanup; exit 130' HUP INT TERM

if [ ! -s "$client_id_file" ] || [ ! -s "$client_secret_file" ]; then
  echo "YAZIO client files are missing; run init-yazio-secrets.sh first." >&2
  exit 1
fi

umask 077
mkdir -p "$secret_dir"
chmod 700 "$secret_dir"
email_tmp=$(mktemp "$secret_dir/.yazio_email.XXXXXX")
password_tmp=$(mktemp "$secret_dir/.yazio_password.XXXXXX")

printf "YAZIO account email: "
IFS= read -r yazio_email

printf "YAZIO account password (hidden): "
terminal_hidden=1
stty -echo
IFS= read -r yazio_password
stty echo
terminal_hidden=0
printf "\n"

if [ -z "$yazio_email" ] || [ -z "$yazio_password" ]; then
  echo "Email and password are required; existing files were not changed." >&2
  exit 1
fi

printf "%s\n" "$yazio_email" > "$email_tmp"
printf "%s\n" "$yazio_password" > "$password_tmp"
chmod 440 "$email_tmp" "$password_tmp"
# Replacing the deliberately read-only destination is the requested operation;
# -f avoids an extra interactive prompt from mv for mode-0440 files.
mv -f "$email_tmp" "$email_file"
email_tmp=""
mv -f "$password_tmp" "$password_file"
password_tmp=""

unset yazio_email yazio_password
trap - EXIT HUP INT TERM
echo "YAZIO account secret files updated with mode 440."
