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

for secret_file in "$email_file" "$password_file" "$client_id_file" "$client_secret_file"; do
  if [ -e "$secret_file" ]; then
    echo "Refusing to overwrite existing secret: $secret_file" >&2
    exit 1
  fi
done

umask 077
mkdir -p "$secret_dir"
chmod 700 "$secret_dir"

terminal_hidden=0
restore_terminal() {
  if [ "$terminal_hidden" -eq 1 ]; then
    stty echo
    terminal_hidden=0
    printf "\n"
  fi
}
trap restore_terminal EXIT
trap 'restore_terminal; exit 130' HUP INT TERM

printf "YAZIO account email: "
IFS= read -r yazio_email

printf "YAZIO account password (hidden): "
terminal_hidden=1
stty -echo
IFS= read -r yazio_password
stty echo
terminal_hidden=0
printf "\n"

printf "Unofficial API client id: "
IFS= read -r yazio_client_id

printf "Unofficial API client secret (hidden): "
terminal_hidden=1
stty -echo
IFS= read -r yazio_client_secret
stty echo
terminal_hidden=0
printf "\n"

if [ -z "$yazio_email" ] || [ -z "$yazio_password" ] || \
   [ -z "$yazio_client_id" ] || [ -z "$yazio_client_secret" ]; then
  echo "Every value is required; no files were written." >&2
  exit 1
fi

printf "%s\n" "$yazio_email" > "$email_file"
printf "%s\n" "$yazio_password" > "$password_file"
printf "%s\n" "$yazio_client_id" > "$client_id_file"
printf "%s\n" "$yazio_client_secret" > "$client_secret_file"
chmod 440 "$email_file" "$password_file" "$client_id_file" "$client_secret_file"

unset yazio_email yazio_password yazio_client_id yazio_client_secret
echo "YAZIO secret files created with mode 440."
echo "Container secret group: $(id -g). Set HOST_SECRET_GID to this value when it is not 1000."
