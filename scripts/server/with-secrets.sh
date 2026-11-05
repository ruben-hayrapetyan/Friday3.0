#!/bin/sh
# Runs a server Friday (friday@.service) with its secrets in its environment, from Bitwarden Secrets Manager (H82):
# the Gmail app password as FRIDAY_SMTP_PASSWORD, read with `bws` using the access token in ~/.config/friday/bws.env
# (BWS_ACCESS_TOKEN=…, readable only by you) and the secret's id in the copy's friday.env (SMTP_SECRET_ID=…).
# Until those are there, sign-in emails are written to the copy's outbox folder instead, and
# scripts/server/last-link.sh prints the newest link (4 Nov: no Gmail app password or Bitwarden account yet).
#   with-secrets.sh COPY COMMAND…
copy="$1"; shift
dir="$HOME/friday-hosted/$copy"
bws="$HOME/.local/bin/bws"
if [ -n "${SMTP_SECRET_ID:-}" ] && [ -r "$HOME/.config/friday/bws.env" ] && [ -x "$bws" ]; then
    . "$HOME/.config/friday/bws.env"
    export BWS_ACCESS_TOKEN
    FRIDAY_SMTP_PASSWORD="$("$bws" secret get "$SMTP_SECRET_ID" --output json \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["value"])')" || FRIDAY_SMTP_PASSWORD=""
    export FRIDAY_SMTP_PASSWORD
    unset BWS_ACCESS_TOKEN
fi
if [ -z "${FRIDAY_SMTP_PASSWORD:-}" ]; then
    export FRIDAY_MAIL_OUTBOX="$dir/outbox"
fi
exec "$@"
