#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check
uv run ruff format --check
uv run pytest -q
# the download site's pages (the hub and the site's server are private, in Friday-admin: its own scripts/check.sh)
uv run --no-project --with pytest pytest -q site-tests
pnpm --dir web typecheck
pnpm --dir web test
# the Mac app, where there is a Swift compiler
if command -v xcrun >/dev/null 2>&1; then Mac/test.sh; fi
