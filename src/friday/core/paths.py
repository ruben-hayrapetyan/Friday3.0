"""Where your own files live: `friday.toml` (DESIGN §22.9) and `secrets.toml` beside it."""

import os
from pathlib import Path


def config_path() -> Path:
    return Path(os.environ.get("FRIDAY_CONFIG", "~/.config/friday/friday.toml")).expanduser()


def secrets_path() -> Path:
    return config_path().with_name("secrets.toml")
