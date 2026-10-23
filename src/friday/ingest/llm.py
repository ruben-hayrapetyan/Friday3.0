"""The Anthropic client (DESIGN §22.5). The key comes from `[anthropic] api_key` in `secrets.toml` beside
`friday.toml`, or else `ANTHROPIC_API_KEY`; it is never stored in settings, exported or logged. The file wins: it is
the one written for Friday, while the variable may be left over in a shell for something else."""

import os
import tomllib
from typing import Any

import anthropic

from friday.core.paths import secrets_path


def api_key() -> str | None:
    return key_source()[0]


def key_source() -> tuple[str | None, str]:
    """The key and where it came from, for saying which one a refusal was about."""
    path = secrets_path()
    found = tomllib.loads(path.read_text()).get("anthropic", {}).get("api_key") if path.exists() else None
    if found:
        return found.strip(), "secrets.toml"
    return os.environ.get("ANTHROPIC_API_KEY") or None, "ANTHROPIC_API_KEY"


def client() -> Any | None:
    key = api_key()
    return anthropic.Anthropic(api_key=key) if key else None
