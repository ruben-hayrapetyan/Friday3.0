#!/bin/bash
# Sets up the server's two Fridays (HOSTED.md S1; H5, H9, H12, H76), with no root:
#   staging  runs this checkout (~/Friday2.0, where the hosted work is done, H6) on 127.0.0.1:8766
#   real     runs its own copy at the commit last released (scripts/server/release.sh) on 127.0.0.1:8765
# each with its own data: the test profiles in ~/friday-hosted/<copy>/profiles, serving one at a time
# (scripts/server/profile.sh). Running it again changes nothing that's there.
set -euo pipefail
export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
hosted="$HOME/friday-hosted"

copy_setup() {  # copy app port
    local dir="$hosted/$1"
    mkdir -p "$dir/config"
    [ -f "$dir/friday.env" ] || printf 'APP=%s\nPROFILE=maya\nPORT=%s\n' "$2" "$3" > "$dir/friday.env"
    if [ ! -d "$dir/profiles" ]; then
        echo "==> Building the test profiles for $1 (about five minutes)"
        (cd "$repo" && FRIDAY_CONFIG=/nonexistent/friday.toml PYTHONPATH=src:. uv run python -m friday.sim.profiles \
            build "$dir/profiles" --jobs 7 2>&1 | grep -E "FAILED|built in" || true)
    fi
}

copy_setup staging "$repo" 8766
[ -d "$hosted/real/app" ] || "$repo/scripts/server/release.sh" --no-restart
copy_setup real "$hosted/real/app" 8765

mkdir -p "$HOME/.config/systemd/user"
cp "$repo/scripts/server/friday@.service" "$HOME/.config/systemd/user/friday@.service"
systemctl --user daemon-reload
systemctl --user enable --now friday@staging friday@real
systemctl --user restart friday@staging friday@real
echo "==> Friday: real on 127.0.0.1:8765, staging on 127.0.0.1:8766"
