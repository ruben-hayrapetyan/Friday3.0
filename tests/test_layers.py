import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"

LAYERS = {
    "core": 0,
    "api": 0,
    "engine": 1,
    "learn": 1,
    "planner": 2,
    "commands": 3,
    "estimate": 3,
    "notify": 3,
    "ingest": 3,
    "sync": 3,
    "integrations": 3,  # C96: to-do apps and other services, on the Inbox's own pieces
    "sim": 3,
    "server": 4,
    "cli": 5,
}
PURE_CORE_MODULES = {"friday.core.time", "friday.core.items", "friday.core.textnorm", "friday.core.pace"}
PURE_THIRD_PARTY = {
    "engine": {"pydantic", "numpy", "numba", "ortools"},
    "learn": {"pydantic", "numpy", "scipy"},
}
LAYER_3_EXCEPTIONS = {
    ("ingest", "friday.estimate"),
    ("ingest", "friday.sync.google_auth"),
    ("sim", "friday.commands"),
    # Integrations bring things in as the Inbox does (commands/suggesting.py), as `Found` inputs (ingest/ics.py), their
    # tokens written as Google's are (sync/google_auth.write_private).
    ("integrations", "friday.commands"),
    ("integrations", "friday.ingest.ics"),
    ("integrations", "friday.sync.google_auth"),
}
# The one script allowed to read the research code, to write the golden fixtures once.
FIXTURE_SCRIPT = ROOT / "scripts" / "make_golden_fixtures.py"


def imported_modules(module: str, is_package: bool, tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
            else:
                parts = module.split(".")
                keep = len(parts) - node.level + (1 if is_package else 0)
                base = ".".join(parts[:keep] + ([node.module] if node.module else []))
            names += [f"{base}.{alias.name}" for alias in node.names]
    return names


def is_within(name: str, prefix: str) -> bool:
    return name == prefix or name.startswith(prefix + ".")


def layer_rule_broken(package: str, target: str, name: str) -> str | None:
    if package == "cli" and not is_within(name, "friday.api"):
        return "cli/ imports only friday.api"
    if LAYERS[target] > LAYERS[package]:
        return "upward import"
    uses_core_io = target == "core" and not any(is_within(name, m) for m in PURE_CORE_MODULES)
    if package in PURE_THIRD_PARTY and uses_core_io:
        return f"{package}/ uses only core time, items, textnorm and pace"
    is_excepted = any(package == p and is_within(name, prefix) for p, prefix in LAYER_3_EXCEPTIONS)
    if LAYERS[package] == LAYERS[target] == 3 and package != "commands" and not is_excepted:
        return "layer-3 packages don't import each other"
    return None


def import_violations(module: str, source: str, is_package: bool = False) -> list[str]:
    parts = module.split(".")
    if len(parts) < 2 or parts[0] != "friday":
        return []
    package = parts[1]
    if package not in LAYERS:
        return [f"{module}: package '{package}' has no layer in tests/test_layers.py"]
    found = []
    for name in imported_modules(module, is_package, ast.parse(source)):
        top = name.split(".")[0]
        if top != "friday":
            allowed = PURE_THIRD_PARTY.get(package)
            if allowed is not None and top not in allowed and top not in sys.stdlib_module_names:
                found.append(f"{module} imports {name}: {package}/ is pure")
            continue
        target = name.split(".")[1] if "." in name else ""
        if target not in LAYERS or target == package:
            continue
        reason = layer_rule_broken(package, target, name)
        if reason:
            found.append(f"{module} imports {name}: {reason}")
    return found


def research_violations(path: Path, source: str) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] if node.level == 0 else []
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and "reference/" in node.value:
            names = ["reference/"]
        else:
            continue
        found += [f"{path.name} uses {name}" for name in names if name == "reference/" or is_within(name, "fr")]
    return found


def module_name(path: Path) -> tuple[str, bool]:
    parts = list(path.relative_to(SRC).with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    return ".".join(parts[:-1] if is_package else parts), is_package


def test_no_module_imports_a_higher_layer() -> None:
    found = []
    for path in sorted(SRC.rglob("*.py")):
        module, is_package = module_name(path)
        found += import_violations(module, path.read_text(), is_package)
    assert found == []


def test_nothing_imports_the_research_code() -> None:
    found = []
    for folder in ("src", "tests", "scripts"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            if path not in (FIXTURE_SCRIPT, Path(__file__).resolve()):
                found += research_violations(path, path.read_text())
    assert found == []


def test_layer_check_catches_each_kind_of_violation() -> None:
    assert import_violations("friday.engine.kernel", "import friday.server.app")
    assert import_violations("friday.engine.kernel", "from ..planner import build")
    assert import_violations("friday.engine.kernel", "from friday.core import db")
    assert import_violations("friday.engine.kernel", "import httpx")
    assert import_violations("friday.cli.main", "from friday.core import dates")
    assert import_violations("friday.notify.push", "from friday.estimate import durations")
    assert import_violations("friday.widgets.x", "")


def test_layer_check_allows_what_the_design_allows() -> None:
    assert not import_violations("friday.engine.kernel", "import numba, numpy, math\nfrom friday.core import time")
    assert not import_violations("friday.engine.rules", "from . import prices", is_package=True)
    assert not import_violations("friday.cli.main", "import typer\nfrom friday.api.commands import PinInput")
    assert not import_violations("friday.ingest.feeds", "from friday.sync.google_auth import token")
    assert not import_violations("friday.commands.items", "from friday.notify import rules")
    assert not import_violations("friday.server.app", "from friday.commands.registry import command")


def test_research_check_catches_imports_and_paths() -> None:
    assert research_violations(Path("x.py"), "from fr.core import grid")
    assert research_violations(Path("x.py"), "import fr")
    assert research_violations(Path("x.py"), "p = 'reference/research/src'")
    assert not research_violations(Path("x.py"), "import friday\nfrom . import fresh")
