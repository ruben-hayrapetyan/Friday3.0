"""What the public repo holds (14 Nov: "clean up the github repo"): the app, its tests and docs. Not your notes, nor
the names of your notes in comments (they aren't in the repo, so a reader can't open them; a comment says its reason
and date instead), nor the internal files taken out: the browser QA checklist, REUSE.md, the design tool's export,
a plugin's config, and the engine research beyond its report (docs/research)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = ("PROGRESS.md", "HOSTED.md", "COMBINED.md", "CLAUDE.md", "PROMPT.md", "claude_design.md", "preferences.md")
NAMED = re.compile("|".join(re.escape(n) for n in NOTES))
KEPT_OUT = ("docs/qa.md", "REUSE.md", "design/", ".ckignore", "BackendGuidelines/", "UI/", *NOTES)


def tracked() -> list[str]:
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True)
    return listed.stdout.split()


def test_no_note_or_internal_file_is_tracked() -> None:
    found = [n for n in tracked() if any(n == k or n.startswith(k) for k in KEPT_OUT)]
    assert not found, found


def test_nothing_names_a_note_that_isnt_in_the_repo() -> None:
    found = []
    for name in tracked():
        own = name in (".gitignore", "tests/test_public_repo.py", "tests/test_us_spelling.py")
        if own or name.startswith("docs/research/"):
            continue  # .gitignore keeps the notes out by name; the research report is quoted as it was written
        try:
            text = (ROOT / name).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        found += [f"{name}:{n}" for n, line in enumerate(text.splitlines(), 1) if NAMED.search(line)]
    assert not found, "\n".join(found[:40])
