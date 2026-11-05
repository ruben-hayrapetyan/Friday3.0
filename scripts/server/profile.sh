#!/bin/bash
# Which test profile a server Friday serves (HOSTED.md H76: one at a time):
#   scripts/server/profile.sh real|staging            the one it serves now
#   scripts/server/profile.sh real|staging list       every profile (key, kind, lived or fresh, who)
#   scripts/server/profile.sh real|staging KEY        serve KEY instead (what you did in the last one is kept)
#   scripts/server/profile.sh real|staging KEY --new  serve KEY rebuilt from scratch, as of now
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
copy="${1:?real or staging}"; key="${2:-}"; dir="$HOME/friday-hosted/$copy"
[ -f "$dir/friday.env" ] || { echo "no $copy Friday here; run scripts/server/install.sh"; exit 1; }
profiles() { (cd "$repo" && PYTHONPATH=src:. uv run python -m friday.sim.profiles "$@"); }
if [ -z "$key" ]; then grep '^PROFILE=' "$dir/friday.env" | cut -d= -f2; exit; fi
if [ "$key" = list ]; then profiles list; exit; fi
profiles list | awk '{print $1}' | grep -qx "$key" || { echo "no profile called $key (try: list)"; exit 1; }
if [ "${3:-}" = --new ]; then
    mv "$dir/profiles/$key" "$dir/profiles/.$key.$(date +%s)" 2>/dev/null || true  # kept, not deleted
fi
[ -f "$dir/profiles/$key/friday.db" ] || FRIDAY_CONFIG=/nonexistent/friday.toml profiles build "$dir/profiles" --only "$key"
sed "s/^PROFILE=.*/PROFILE=$key/" "$dir/friday.env" > "$dir/friday.env.new" && mv "$dir/friday.env.new" "$dir/friday.env"
systemctl --user restart "friday@$copy"
echo "==> $copy Friday now serves $(profiles list | grep "^$key ")"
