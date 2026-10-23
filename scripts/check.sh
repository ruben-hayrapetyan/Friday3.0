#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

uv run ruff check
uv run ruff format --check
uv run pytest -q
pnpm --dir web typecheck
pnpm --dir web test
# the Mac app, where there is a Swift compiler
if command -v xcrun >/dev/null 2>&1; then Mac/test.sh; fi
