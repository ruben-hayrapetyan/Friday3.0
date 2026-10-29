"""Python rule plugins (DESIGN §17.4): every `*.py` in the rules folder is imported, so its `@rule_type` classes
register. Both the API process and the worker load them; a failing file is skipped and named with `file:line`."""

import importlib.util
import traceback
from pathlib import Path

from friday.core.paths import config_path

# Beside friday.toml (~/.config/friday/rules), so a Friday given its own config (FRIDAY_CONFIG: a fresh-user sandbox,
# scripts/fresh_user.sh) has its own plugins, none at first, rather than yours.
PLUGIN_DIR = config_path().with_name("rules")


def load_plugins(directory: Path = PLUGIN_DIR) -> list[str]:
    """Import each plugin file; returns one `file:line: error` per file that failed."""
    errors = []
    for path in sorted(directory.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"friday_plugin_{path.stem}", path)
        try:
            module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as error:  # a plugin can raise anything; it is skipped, not fatal
            errors.append(f"{where(path, error)}: {type(error).__name__}: {error}")
    return errors


def where(path: Path, error: Exception) -> str:
    if isinstance(error, SyntaxError) and error.lineno:
        return f"{path}:{error.lineno}"
    lines = [f.lineno for f in traceback.extract_tb(error.__traceback__) if Path(f.filename) == path]
    return f"{path}:{lines[-1]}" if lines else str(path)
