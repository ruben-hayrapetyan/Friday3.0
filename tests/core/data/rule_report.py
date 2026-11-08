"""How the rule reader does on every labelled set (tests/core/test_rule_sentences.py's corpora, its comparison), by
set and kind: `PYTHONPATH=src:. uv run python -m tests.core.data.rule_report [SET] [--misses KIND|unread|misread|all]`.
A rule read right; misread (read as something it doesn't mean: the one thing never allowed); unread (left to the AI);
for what isn't one rule ("multi", "item", "set:…", "new:…"), left to the AI or read anyway."""

import sys
from collections import Counter, defaultdict

from friday.core.rule_text import read
from tests.core.test_rule_sentences import ALLOWED, CORPORA, differences


def outcome(text: str, want: object) -> tuple[str, str]:
    reading, _ = read(text)
    if not isinstance(want, dict):
        return ("left" if reading is None or text in ALLOWED else "read_anyway",
                "" if reading is None else f"{reading.kind} {reading.subject}")  # fmt: skip
    if reading is None:
        return "unread", ""
    off = differences(want, reading)
    return ("right", "") if not off else ("misread", ", ".join(off))


def main() -> None:
    args = sys.argv[1:]
    show = args[args.index("--misses") + 1] if "--misses" in args else None
    sets = [a for a in args if a in CORPORA] or list(CORPORA)
    for name in sets:
        by_kind: dict[str, Counter] = defaultdict(Counter)
        misses = []
        for _topic, text, want in CORPORA[name]:
            kind = want["kind"] if isinstance(want, dict) else str(want).split(":")[0]
            result, why = outcome(text, want)
            by_kind[kind][result] += 1
            if result not in ("right", "left"):
                misses.append((kind, result, text, why, want))
        rules = sum(c["right"] + c["misread"] + c["unread"] for c in by_kind.values())
        right = sum(c["right"] for c in by_kind.values())
        print(f"\n{name}: {right}/{rules} rules read right ({100 * right / max(rules, 1):.0f}%)")
        for kind in sorted(by_kind):
            c = by_kind[kind]
            print(f"  {kind:20} " + "  ".join(f"{k} {v}" for k, v in sorted(c.items())))
        for kind, result, text, why, want in misses:
            if show in ("all", kind, result):
                print(f"  [{result}] {kind}: {text!r}  {why}  want={want}")


if __name__ == "__main__":
    main()
