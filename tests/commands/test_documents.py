"""Uploaded syllabi: what each one became (read, waiting in the inbox, failed and why), reading a failed one again,
and a PDF read for the claude command, which takes text, by pdftotext."""

import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from friday.core.items import FieldError
from friday.ingest.llm import CliClient, pdf_text
from tests.commands.helpers import App, new_app

PDF = Path(__file__).parents[1] / "fixtures" / "syllabus-line.pdf"


@pytest.fixture
def app(tmp_path: Path) -> App:
    return new_app(tmp_path)


def test_each_upload_says_what_it_became(app: App) -> None:
    app.do("document_add", name="CS syllabus.txt", content="PS1 due Friday 5pm. PS2 due next Friday 5pm.")
    app.do("document_add", name="Chem.pdf", media_type="application/pdf", content="JVBERi0=")
    (chem, cs) = app.do("documents")
    assert (chem["name"], chem["kind"], chem["status"]) == ("Chem.pdf", "pdf", "reading")
    assert (cs["name"], cs["kind"], cs["status"]) == ("CS syllabus.txt", "text", "reading")
    raw = {r["title"]: r["id"] for r in app.table("raw_inputs")}
    app.conn.execute("UPDATE raw_inputs SET status = 'failed', error = 'no key' WHERE id = ?", [raw["Chem.pdf"]])
    failed = app.do("documents")[0]
    assert (failed["status"], failed["error"]) == ("failed", "no key")
    out = app.do("document_retry", id=failed["id"])
    assert out["message"].startswith("Reading Chem.pdf again")
    assert app.do("documents")[0]["status"] == "reading"
    with pytest.raises(FieldError, match="isn't one that failed"):
        app.do("document_retry", id=failed["id"])


def test_what_a_read_syllabus_found_is_counted(app: App) -> None:
    app.do("document_add", name="CS syllabus.txt", content="PS1 due Friday 5pm.")
    raw = app.table("raw_inputs")[-1]["id"]
    app.conn.execute("UPDATE raw_inputs SET status = 'extracted' WHERE id = ?", [raw])
    for status in ("pending", "accepted", "rejected"):
        app.conn.execute(
            "INSERT INTO suggestions (user_id, raw_input_id, command, input, status, created_utc) "
            "VALUES (1, ?, 'add', '{}', ?, '2026-10-19T13:00Z')",
            [raw, status],
        )
    (doc,) = app.do("documents")
    assert (doc["status"], doc["found"], doc["waiting"], doc["accepted"]) == ("read", 3, 1, 1)


NO_PDFTOTEXT = shutil.which("pdftotext") is None and not Path("/opt/homebrew/bin/pdftotext").exists()


@pytest.mark.skipif(
    shutil.which("pdftotext") is None and not Path("/opt/homebrew/bin/pdftotext").exists(), reason="no pdftotext"
)
def test_a_pdf_goes_to_the_claude_command_as_its_text() -> None:
    assert pdf_text(PDF.read_bytes()) == "CHEM 2090 Problem Set 3 due October 30"
    seen = {}

    def run(args, **kwargs):  # the claude command, as a fake: what it was handed
        seen["prompt"] = kwargs["input"]  # the prompt goes in on stdin

        class Out:
            returncode, stdout, stderr = 0, '{"result": "{}", "usage": {}}', ""

        return Out()

    document = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                               "data": base64.b64encode(PDF.read_bytes()).decode()}}  # fmt: skip
    message = {"role": "user", "content": [document, {"type": "text", "text": "Find the due dates."}]}
    CliClient(Path("/bin/claude"), run=run).create(model="m", system="s", messages=[message])
    assert "CHEM 2090 Problem Set 3 due October 30" in seen["prompt"] and "Find the due dates." in seen["prompt"]


def test_an_image_goes_to_the_command_as_a_file_it_reads() -> None:
    """29 Oct ("friday should use the cli whenever it can to not use the API"): no key for a photo either."""
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}}
    handed: dict = {}

    def run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        handed.update(args=args, files=[p.name for p in Path(str(kwargs["cwd"])).iterdir()])
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps({"result": "a photo"}), stderr="")

    reply = CliClient(Path("/bin/claude"), run=run).create(
        model="m", system="s", messages=[{"role": "user", "content": [image]}]
    )
    assert reply.content[0].text == "a photo" and handed["files"] == ["image-1.png"] and "Read" in handed["args"]


SYLLABUS_PAGE = """<!DOCTYPE html><html><head><title>CS 2112</title><style>p{color:red}</style>
<script>var tracking = 1;</script></head><body><nav>Home | Grades</nav>
<h1>CS 2112 Fall 2026</h1><p>Lectures Tue &amp; Thu 10:10&ndash;11:25am.</p>
<table><tr><th>Week</th><th>Due</th></tr><tr><td>3</td><td>PS 3 due Oct 30</td></tr></table>
<ul><li>Prelim 1: Oct 8, 7:30pm</li></ul></body></html>"""


def test_a_saved_web_page_is_read_as_its_text(app: App) -> None:
    from friday.core.html_text import html_text

    assert html_text(SYLLABUS_PAGE).splitlines() == [
        "CS 2112 Fall 2026",
        "Lectures Tue & Thu 10:10–11:25am.",
        "Week | Due",
        "3 | PS 3 due Oct 30",
        "- Prelim 1: Oct 8, 7:30pm",
    ]
    app.do("document_add", name="CS 2112 Syllabus.html", media_type="text/html", content=SYLLABUS_PAGE)
    raw = app.table("raw_inputs")[-1]
    assert raw["media_type"] == "text/plain"
    assert "PS 3 due Oct 30" in raw["content"] and "tracking" not in raw["content"]
    with pytest.raises(FieldError, match="no text"):
        app.do("document_add", name="empty.html", content="<html><script>x</script></html>")
