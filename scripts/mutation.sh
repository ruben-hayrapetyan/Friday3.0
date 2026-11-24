#!/usr/bin/env bash
# The depth check (TESTING.md, "What in depth means"): mutmut changes the code of one module at a time on purpose (a
# `<` made `<=`, a branch taken away, a number off by one, a string changed) and runs the tests that reach each change;
# every change must fail a test. What survives is a missing test, listed at the end with the change that survived.
# Heavy: run it on debian (remote-run, ~/.claude/CLAUDE.md):
#
#   remote-run -o .mutants -- sh -c 'export PATH="$HOME/.local/bin:$PATH"; scripts/mutation.sh src/friday/commands/tips.py'
#
# MODULE: a file or folder under src/friday (default: all of it, which takes hours); TESTS: the tests to run against it
# (default: every test but the system, stress and bench ones; name the module's own tests for a quick look). Results
# in .mutants/ (git ignores it): survivors.txt, one surviving change a line, and score.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
MODULE="${1:-src/friday}"
TESTS="${2:-tests/}"
[ -e "$MODULE" ] || { echo "no $MODULE" >&2; exit 1; }
mkdir -p .mutants
# mutmut 3 reads its settings from setup.cfg: this run's own, kept out of git
cp setup.cfg .mutants/setup.cfg.kept 2>/dev/null || true
trap 'if [ -f .mutants/setup.cfg.kept ]; then mv .mutants/setup.cfg.kept setup.cfg; else rm -f setup.cfg; fi' EXIT
cat > setup.cfg <<EOF
[mutmut]
paths_to_mutate=$MODULE
also_copy=
    src/
    tests/
    VERSION
tests_dir=$TESTS
pytest_add_cli_args=
    -p
    no:cacheprovider
    --ignore=tests/system
    --ignore=tests/stress
    --ignore=tests/bench
EOF
uv run --with "mutmut>=3.3" mutmut run || true
uv run --with "mutmut>=3.3" mutmut results 2>/dev/null | grep -E ": (survived|no tests|timeout)" > .mutants/survivors.txt || true
total="$(uv run --with "mutmut>=3.3" mutmut results --all true 2>/dev/null | grep -c ':' || true)"
left="$(wc -l < .mutants/survivors.txt | tr -d ' ')"
echo "$MODULE: $left of $total changes survived" | tee .mutants/score.txt
