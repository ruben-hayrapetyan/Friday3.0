"""Wraps each page body (pages/*.html: a title and description, ---, then the body) in the site's header and footer,
writing plain HTML into site/. Run after editing a page; the output is what's served."""

import html
from pathlib import Path

HERE = Path(__file__).parent
NAV = [("features.html", "Features"), ("help.html", "Help"), ("whats-new.html", "What's new"),
       ("privacy.html", "Privacy")]


def page(name: str, title: str, description: str, body: str) -> str:
    links = "\n    ".join(
        f'<a href="/{href}"{" aria-current=\"page\"" if href == name else ""}>{label}</a>' for href, label in NAV
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
</div></footer>
<script src="/site.js"></script>
</body>
</html>
"""


for source in sorted((HERE / "pages").glob("*.html")):
    head, body = source.read_text().split("---\n", 1)
    meta = dict(line.split(": ", 1) for line in head.strip().splitlines())
    (HERE / "site" / source.name).write_text(page(source.name, meta["title"], meta["description"], body))
    print("wrote", source.name)
