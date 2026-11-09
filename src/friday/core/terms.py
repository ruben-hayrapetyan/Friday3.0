"""Friday's terms (PROGRESS.md C71): the text everyone accepts when Friday first opens, and again each time it
changes. The text is `terms.md` beside this file (TERMS.md at the top of the repo is the same, for readers on
GitHub); its `Version:` line names it, and its "What changed" list is what the app shows someone who accepted an
earlier version."""

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

TEXT = Path(__file__).with_name("terms.md")
VERSION = re.compile(r"^Version: (\S+)$", re.MULTILINE)


@dataclass(frozen=True)
class Terms:
    version: str
    text: str  # the whole document, markdown
    changes: tuple[str, ...]  # "What changed", one line each


@cache
def current() -> Terms:
    text = TEXT.read_text(encoding="utf-8")
    found = VERSION.search(text)
    if found is None:
        raise ValueError("terms.md has no Version: line")
    return Terms(found[1], text, changes_in(text))


def changes_in(text: str) -> tuple[str, ...]:
    """The bullets under "## What changed", up to the next heading."""
    part = text.split("## What changed", 1)[1] if "## What changed" in text else ""
    part = part.split("\n## ", 1)[0]
    return tuple(line[2:].strip() for line in part.splitlines() if line.startswith("- "))
