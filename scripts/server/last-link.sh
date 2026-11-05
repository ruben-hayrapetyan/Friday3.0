#!/bin/sh
# The newest sign-in link a server Friday wrote to its outbox, while it can't send mail yet (with-secrets.sh):
#   scripts/server/last-link.sh real|staging
copy="${1:?real or staging}"
newest="$(ls -t "$HOME/friday-hosted/$copy/outbox/"*.eml 2>/dev/null | head -1)"
[ -n "$newest" ] || { echo "no sign-in email in $copy's outbox yet: ask for a link on the sign-in page first"; exit 1; }
python3 - "$newest" <<'PY'
import re, sys
from email import message_from_bytes
body = message_from_bytes(open(sys.argv[1], "rb").read()).get_payload(decode=True).decode()
print(re.search(r"https?://\S+/auth/link\?t=\S+", body).group(0))
PY
