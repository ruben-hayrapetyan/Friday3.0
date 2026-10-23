"""Write `src/friday/api/verbs.py`, the command list the CLI is generated from (it may import only friday.api), and
`web/openapi.json`, which `pnpm --dir web gen:api` turns into the web app's types.

Run after adding or changing a command: `PYTHONPATH=src:. uv run python -m scripts.make_verbs`.
`tests/test_verbs.py` fails while either file is out of date.
"""

import json
import subprocess
from pathlib import Path

from friday.api.types import Verb
from friday.commands.all import REGISTRY
from friday.server.app import create_app

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "friday" / "api" / "verbs.py"
OPENAPI = ROOT / "web" / "openapi.json"


def openapi() -> str:
    return json.dumps(create_app(Path("unused.db"), background=False).openapi(), indent=1) + "\n"


def verbs() -> dict[str, Verb]:
    """Each registry entry with the route the server gives it."""
    app = create_app(Path("unused.db"), background=False)
    routes = {r.operation_id: r for r in app.routes if hasattr(r, "operation_id")}  # type: ignore[attr-defined]
    return {
        name: Verb(
            next(iter(routes[name].methods)),
            routes[name].path,
            spec.input_type,
            spec.mutates,
            spec.affects_plan,
            spec.summary,
        )
        for name, spec in sorted(REGISTRY.items())
    }


def source() -> str:
    lines = [
        '"""Every command and query, for the CLI. Written by `scripts/make_verbs.py`; don\'t edit."""',
        "",
        "from friday.api import commands",
        "from friday.api.types import Verb",
        "",
        "VERBS = {",
    ]
    for name, v in verbs().items():
        lines.append(
            f"    {name!r}: Verb({v.method!r}, {v.path!r}, commands.{v.input.__name__}, "
            f"{v.mutates}, {v.affects_plan}, {v.summary!r}),"
        )
    return "\n".join([*lines, "}", ""])


if __name__ == "__main__":
    TARGET.write_text(source())
    subprocess.run(["ruff", "format", "-q", str(TARGET)], check=True)
    OPENAPI.write_text(openapi())
    print(f"wrote {TARGET} and {OPENAPI}; now run `pnpm --dir web gen:api`")
