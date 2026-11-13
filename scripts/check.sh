#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check
uv run ruff format --check
uv run pytest  # already -q (pyproject addopts): another -q hides the pass and fail counts
# the download site's pages (the hub and the site's server are private, in Friday-admin: its own scripts/check.sh)
uv run --no-project --with pytest pytest -q site-tests
# the pnpm web/package.json names, through npx: a fresh machine set up as the README says has no pnpm of its own
npx --yes pnpm@10.12.1 --dir web typecheck
npx --yes pnpm@10.12.1 --dir web test
# the Mac app, where there is a Swift compiler
if command -v xcrun >/dev/null 2>&1; then Mac/test.sh; fi
