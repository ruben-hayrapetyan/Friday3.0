#!/bin/bash
# Moves the real Friday to a commit that staging has run (HOSTED.md H9: changes reach staging first):
#   scripts/server/release.sh [COMMIT] [--no-restart]     default: this checkout's HEAD
# The real copy is a worktree of this checkout at ~/friday-hosted/real/app, with its own Python and web build.
set -euo pipefail
export PATH="$HOME/.local/node/bin:$HOME/.local/bin:$PATH"
repo="$(cd "$(dirname "$0")/../.." && pwd)"
app="$HOME/friday-hosted/real/app"
commit="HEAD"; restart=1
for a in "$@"; do case "$a" in --no-restart) restart=0 ;; *) commit="$a" ;; esac; done
# What isn't committed isn't released (4 Nov: new server scripts left out took the real copy down for minutes).
if [ "$commit" = HEAD ] && ! git -C "$repo" diff --quiet HEAD -- src scripts web/src pyproject.toml uv.lock; then
    echo "uncommitted changes in $repo wouldn't be released: commit them first"; exit 1
fi
if [ "$commit" = HEAD ] && [ -n "$(git -C "$repo" ls-files --others --exclude-standard -- src scripts web/src)" ]; then
    echo "new files in $repo aren't committed, so they wouldn't be released: commit them first"; exit 1
fi
commit="$(git -C "$repo" rev-parse "$commit")"
if [ -d "$app" ]; then git -C "$app" checkout -q --detach "$commit"
else mkdir -p "$(dirname "$app")" && git -C "$repo" worktree add -q --detach "$app" "$commit"; fi
echo "==> Real Friday at $(git -C "$app" log --oneline -1)"
(cd "$app" && uv sync -q && npx --yes pnpm@10.12.1 --dir web install --frozen-lockfile --silent \
    && npx --yes pnpm@10.12.1 --dir web build > /dev/null)
if [ "$restart" = 1 ]; then systemctl --user restart friday@real && echo "==> Restarted"; fi
