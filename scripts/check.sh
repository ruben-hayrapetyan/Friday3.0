#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check
uv run ruff format --check
uv run pytest -q
# the download site and the admin hub (HOSTED.md H168): the hub is its own project, with its own packages
(cd hub && uv run --frozen pytest -q)
uv run --no-project --with pytest pytest -q site-tests
pnpm --dir web typecheck
pnpm --dir web test
# the Mac app, where there is a Swift compiler
if command -v xcrun >/dev/null 2>&1; then Mac/test.sh; fi
