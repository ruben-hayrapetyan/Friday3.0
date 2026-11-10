"""Writes the site's pages into site/ from pages/*.html (a title and description, ---, then the body): each wrapped
in the site's header and footer, except one marked `wrap: no` (the home page, a whole document of its own).

The current version (releases/released.json, written by the hub's Release and Roll back, HOSTED.md H134–H142) fills
{{version}}, {{dmg}} and {{size}} in every page, and {{versions}} becomes What's new: every offered version's
notes, newest first (H142). Run after editing a page; the hub runs it at every Release."""

import html
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE / "hub"))
from friday_hub import notes as notes_  # noqa: E402  (the hub's own notes, shown the same everywhere)

NAV = [
    ("features.html", "Features"),
    ("help.html", "Help"),
    ("whats-new.html", "What's new"),
    ("privacy.html", "Privacy"),
    ("contact.html", "Contact"),
]


FOOT = [*NAV, ("terms.html", "Terms")]  # the terms in the footer only: the header stays lean (H176)
TERMS = (
    "TERMS.md"  # the app's own terms (tests/commands/test_terms.py keeps it the same), so the two never differ (C71)
)


def page(name: str, title: str, description: str, body: str) -> str:
    links = "\n    ".join(
        f'<a href="/{href}"{' aria-current="page"' if href == name else ""}>{label}</a>' for href, label in NAV
    )
    foot = "\n  ".join(f'<a href="/{href}">{label}</a>' for href, label in FOOT)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
<link rel="icon" href="/images/icon.png">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="site"><div class="wrap">
  <a class="mark" href="/"><img src="/images/icon.png" alt="" width="28" height="28">Friday</a>
  <nav class="pages" aria-label="Pages">
    {links}
  </nav>
  <a class="button small" href="/#get">Download</a>
</div></header>

<main class="page"><div class="wrap">
{body.strip()}
</div></main>

<footer class="site"><div class="wrap">
  <span class="spacer"><img src="/images/icon.png" alt="" width="18" height="18">Friday · free, its code open to read</span>
  {foot}
  <a href="mailto:friday_support@friday-scheduler.com">friday_support@friday-scheduler.com</a>
</div></footer>
<script src="/site.js"></script>
</body>
</html>
"""


def offered(record: dict) -> list[dict]:
    top = tuple(int(p) for p in record["current"].split("."))
    found = [v for v in record["versions"] if tuple(int(p) for p in v["version"].split(".")) <= top]
    return sorted(found, key=lambda v: tuple(int(p) for p in v["version"].split(".")), reverse=True)


def versions(record: dict) -> str:
    """What's new: each offered version's notes; the current one with its download."""
    parts = []
    for v in offered(record):
        name = html.escape(v["version"])
        download = (f' · <a href="/get/Friday-{name}.dmg" download>Download</a>'
                    if v["version"] == record["current"] else "")  # fmt: skip
        parts.append(f"""<div class="version" id="{name}">
  <h2>Friday {name}</h2>
  <p class="when">{notes_.long_date(v["released"])}{download}</p>
{notes_.sections_html(v["notes"])}
</div>""")
    return "\n\n".join(parts)


INLINE = re.compile(r"\*\*([^*]+)\*\*|`([^`]+)`|&lt;(https?://[^\s&]+)&gt;")


def inline(text: str) -> str:
    """A line of the terms, escaped, with its **bold**, `code` and <links> as HTML."""

    def one(m: re.Match[str]) -> str:
        if m[1]:
            return f"<b>{m[1]}</b>"
        if m[2]:
            return f"<code>{m[2]}</code>"
        here = m[3].removeprefix("https://friday-scheduler.com")  # the site's own pages, linked as its own
        return f'<a href="{here or "/"}">{m[3]}</a>'

    return INLINE.sub(one, html.escape(text, quote=False))


def terms_html(markdown: str) -> str:
    """The terms' markdown as the site's HTML: the title, the version as a date line, headings, paragraphs, lists.
    "What changed" is for the app's popup, not the page."""
    out, skip = [], False
    for chunk in markdown.split("\n\n"):
        lines = [line for line in chunk.strip().splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0]
        if first.startswith("## "):
            skip = first == "## What changed"
            if not skip:
                out.append(f"<h2>{inline(first[3:])}</h2>")
        elif skip:
            continue
        elif first.startswith("# "):
            out.append(f"<h1>{inline(first[2:])}</h1>")
        elif first.startswith("Version: "):
            out.append(f'<p class="when">Version of {notes_.long_date(first[9:19])}</p>')  # "2026-11-09.2" is that day
        elif all(line.startswith("- ") for line in lines):
            out.append("<ul>\n" + "\n".join(f"  <li>{inline(line[2:])}</li>" for line in lines) + "\n</ul>")
        else:
            out.append(f"<p>{inline(' '.join(lines))}</p>")
    return "\n".join(out)


def fill(body: str, record: dict, root: Path = HERE) -> str:
    live = next(v for v in record["versions"] if v["version"] == record["current"])
    if "{{terms}}" in body:
        body = body.replace("{{terms}}", terms_html((root / TERMS).read_text()))
    return (body.replace("{{versions}}", versions(record))
            .replace("{{version}}", live["version"])
            .replace("{{dmg}}", f"/get/Friday-{live['version']}.dmg")
            .replace("{{size}}", notes_.megabytes(live["bytes"])))  # fmt: skip


def build(root: Path = HERE) -> list[str]:
    record = json.loads((root / "releases" / "released.json").read_text())
    written = []
    for source in sorted((root / "pages").glob("*.html")):
        head, body = source.read_text().split("---\n", 1)
        meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
        body = fill(body, record, root)
        text = body if meta.get("wrap") == "no" else page(source.name, meta["title"], meta["description"], body)
        (root / "site" / source.name).write_text(text)
        written.append(source.name)
    return written


if __name__ == "__main__":
    for name in build():
        print("wrote", name)
