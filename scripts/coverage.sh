#!/usr/bin/env bash
# What the tests run and what they don't (11 Nov: "do the coverage check"). Not part of scripts/check.sh: it runs
# every test again, slower, and changes nothing. Python: every test, the servers the system tests start counted too
# (coverage follows them into their own processes); the website: its tests over all of web/src. Reports in
# coverage/ (Python, as HTML) and web/coverage/ (the website's), both left out of git.
set -euo pipefail
cd "$(dirname "$0")/.."

mkdir -p coverage
cat > coverage/rc <<EOF
[run]
source = src/friday
branch = true
parallel = true
patch = subprocess
sigterm = true
data_file = $PWD/coverage/.coverage
[report]
skip_empty = true
[html]
directory = coverage/py
EOF
uv run --with pytest-cov --with "coverage>=7.10" pytest -q -p no:cacheprovider --cov --cov-config=coverage/rc \
  --cov-report=term:skip-covered --cov-report=html
pnpm --dir web coverage
echo "Python: coverage/py/index.html · website: web/coverage/index.html"
