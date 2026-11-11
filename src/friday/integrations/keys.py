"""Friday's own app ids and secrets at the services it signs in to (Trello, Microsoft, TickTick, Slack; 11 Nov: "they
should be kept out of the github repos"). Never in the code: read from, in order, an environment variable
(FRIDAY_<NAME>, for tests and scripts), the copy Mac/bundle.sh puts beside the server's Python
(share/friday/app_keys.json), or Mac/app_keys.json in the checkout (running from source). That file is gitignored and
tests/test_keys_out_of_git.py fails if any of its values is in a tracked file. A key not found is "": the service's
box says it isn't ready in this copy of Friday."""

import json
import os
import sys
from functools import cache
from pathlib import Path
from typing import Any

FILE = "app_keys.json"
PLACES = [
    Path(sys.prefix) / "share" / "friday" / FILE,  # in Friday.app (Mac/bundle.sh)
    Path(__file__).resolve().parents[3] / "Mac" / FILE,  # the checkout, running from source
]


@cache
def kept() -> dict[str, Any]:
    for place in PLACES:
        try:
            found = json.loads(place.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(found, dict):
            return found
    return {}


def get(name: str) -> str:
    """A key by its name ("trello_client_id"): FRIDAY_TRELLO_CLIENT_ID, else the keys file, else ""."""
    return str(os.environ.get(f"FRIDAY_{name.upper()}") or kept().get(name) or "").strip()
