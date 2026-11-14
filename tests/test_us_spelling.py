"""Friday is written in US English (13 Nov, from a client's notes: "grey is also the UK spelling, also several
instances of spellings like 'colour'"; the user: "the spellings should all be US not UK"). Every tracked text file: the
app's words, the site, the Mac app, the docs and comments. "Cancelled" isn't checked: it's also Google's event status
and the code's job flags, so the words people read say "canceled" by hand (the sign-in message)."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UK = (
    "colour colours coloured colouring recolour recolours recoloured grey greys greyed greyish centre centres centred "
    "centring licence licences neighbour neighbours neighbouring behaviour behaviours labelled unlabelled labelling "
    "minimise minimises minimised honour honours honoured favourite favourites"
).split()
FOUND = re.compile(r"(?<![A-Za-z])(" + "|".join(UK) + r")(?![A-Za-z])", re.I)
NOT_OURS = re.compile(r"(^|/)(pnpm-lock\.yaml|uv\.lock)$|\.(woff2?|png|jpg|ico|icns|pdf|bundle)$")


def test_no_uk_spellings_in_what_friday_says_or_ships() -> None:
    names = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True).stdout
    found = []
    for name in names.split():
        if NOT_OURS.search(name) or name == "tests/test_us_spelling.py":
            continue
        try:
            text = (ROOT / name).read_text()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if FOUND.search(line):
                found.append(f"{name}:{n}: {FOUND.search(line)[0]}")
    assert not found, "UK spellings (Friday is in US English):\n" + "\n".join(found[:40])


def test_a_canceled_sign_in_says_canceled() -> None:
    assert '"Sign-in canceled."' in (ROOT / "src" / "friday" / "commands" / "connecting.py").read_text()
