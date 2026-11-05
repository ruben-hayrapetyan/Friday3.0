#!/bin/sh
# Runs a server Friday (friday@.service) with its secrets in its environment, from Bitwarden Secrets Manager (H82),
# read with `bws` using the access token in ~/.config/friday/bws.env (BWS_ACCESS_TOKEN=…, readable only by you):
#   SMTP_SECRET_ID   → FRIDAY_SMTP_PASSWORD         the Gmail app password (its spaces, as Google shows it, left out)
#   GOOGLE_SECRET_ID → FRIDAY_GOOGLE_CLIENT_SECRET  Sign in with Google's client secret (its id: FRIDAY_GOOGLE_CLIENT_ID)
# the ids in the copy's friday.env. Without a mail password, sign-in emails go to the copy's outbox folder instead
# (scripts/server/last-link.sh prints the newest link).
#   with-secrets.sh COPY COMMAND…
copy="$1"; shift
dir="$HOME/friday-hosted/$copy"
bws="$HOME/.local/bin/bws"
secret() {  # the value of the secret with this id, or nothing
    [ -n "$1" ] && [ -r "$HOME/.config/friday/bws.env" ] && [ -x "$bws" ] || return 0
    (. "$HOME/.config/friday/bws.env"; export BWS_ACCESS_TOKEN; "$bws" secret get "$1" --output json 2>/dev/null) \
        | python3 -c 'import json, sys; print(json.load(sys.stdin)["value"].strip())' 2>/dev/null
}
FRIDAY_SMTP_PASSWORD="$(secret "${SMTP_SECRET_ID:-}" | tr -d ' ')"
FRIDAY_GOOGLE_CLIENT_SECRET="$(secret "${GOOGLE_SECRET_ID:-}")"
export FRIDAY_SMTP_PASSWORD FRIDAY_GOOGLE_CLIENT_SECRET
[ -n "$FRIDAY_SMTP_PASSWORD" ] || export FRIDAY_MAIL_OUTBOX="$dir/outbox"
exec "$@"
