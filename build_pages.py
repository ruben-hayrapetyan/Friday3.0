"""Writes the site's pages into site/ from pages/*.html (a title and description, ---, then the body): each wrapped
in the site's header and footer, except one marked `wrap: no` (the home page, a whole document of its own).

The current version (releases/released.json, written by the hub's Release and Roll back, HOSTED.md H134–H142) fills
{{version}}, {{dmg}} and {{size}} in every page, and {{versions}} becomes What's new: every offered version's
notes, newest first (H142). Run after editing a page; the hub runs it at every Release."""

import html
import json
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


def page(name: str, title: str, description: str, body: str) -> str:
    links = "\n    ".join(
        f'<a href="/{href}"{' aria-current="page"' if href == name else ""}>{label}</a>' for href, label in NAV
    )
    foot = "\n  ".join(f'<a href="/{href}">{label}</a>' for href, label in NAV)
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
  <span class="spacer"><img src="/images/icon.png" alt="" width="18" height="18">Friday · free, and open source soon</span>
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


def fill(body: str, record: dict) -> str:
    live = next(v for v in record["versions"] if v["version"] == record["current"])
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
        body = fill(body, record)
        text = body if meta.get("wrap") == "no" else page(source.name, meta["title"], meta["description"], body)
        (root / "site" / source.name).write_text(text)
        written.append(source.name)
    return written


if __name__ == "__main__":
    for name in build():
        print("wrote", name)
