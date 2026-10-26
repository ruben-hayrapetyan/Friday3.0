"""A web page as the text a reader sees (a syllabus saved from Canvas, say), for reading tasks out of it: no scripts,
styles or navigation; each paragraph, heading and list item on its own line; a table's cells side by side in a row
("Week 3 | Oct 30 | PS 3 due"), so a schedule of due dates reads as one. Standard library only."""

import re
from html.parser import HTMLParser

SKIP = {"script", "style", "noscript", "template", "svg", "head", "nav", "button", "select", "form"}
BLOCK = {
    "p", "div", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article", "header",
    "footer", "main", "ul", "ol", "dl", "dt", "dd", "blockquote", "pre", "hr", "caption", "thead", "tbody", "aside",
}  # fmt: skip
CELL = {"td", "th"}


class Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0
        self.cells_in_row = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP:
            self.skipping += 1
        elif tag in CELL:
            self.parts.append(" | " if self.cells_in_row else "")
            self.cells_in_row += 1
        elif tag in BLOCK:
            self.parts.append("\n")
            if tag == "tr":
                self.cells_in_row = 0
        elif tag == "li":
            self.parts.append("\n- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("br", "hr"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def html_text(html: str) -> str:
    reader = Reader()
    reader.feed(html)
    reader.close()
    lines = (re.sub(r"[ \t\r\f\v ]+", " ", line).strip(" |") for line in "".join(reader.parts).split("\n"))
    kept = [line.strip() for line in lines if line.strip()]
    return "\n".join(kept)


def looks_like_html(name: str, media_type: str, content: str) -> bool:
    head = content.lstrip()[:200].lower()
    return (
        media_type == "text/html"
        or name.lower().endswith((".html", ".htm"))
        or head.startswith(("<!doctype html", "<html"))
    )
