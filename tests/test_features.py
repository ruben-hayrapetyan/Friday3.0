"""Every feature tested in every layer (24 Nov, the user: "go through every single functionality of the app and build an
extensive test suite (both web, headless, and regular) ... i want to make sure that absolutely nothing can break
without our tests flagging it"). tests/features.toml names each feature and the commands and queries it runs; here:

- every command and query belongs to exactly one feature (a new one without a feature fails);
- regular: each is named in a Python test of its own code (tests/, outside the system tests);
- headless: each is sent to a real `fridayd` over HTTP in a system test (tests/system/), the whole pipeline;
- web: each feature with a page has a browser test that drives it in Chrome (web/e2e/<feature>.e2e.mjs).

What isn't done yet is listed in tests/features_todo.txt, one "feature layer" or "command layer" a line; the list
only shrinks: a gap not listed fails, and so does a listed one that's been filled (take it off). TESTING.md says how."""

import re
import tomllib
from functools import cache
from pathlib import Path

import friday.commands.all  # noqa: F401  (registers every command and query)
from friday.commands.registry import REGISTRY

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
E2E = ROOT / "web" / "e2e"
TODO = TESTS / "features_todo.txt"


def features() -> list[dict]:
    return tomllib.loads((TESTS / "features.toml").read_text())["feature"]


@cache
def texts(system: bool) -> tuple[str, ...]:
    """The Python tests' text: the system tests (`system`), or every other."""
    found = []
    for path in TESTS.rglob("test_*.py"):
        if path.name == "test_features.py":
            continue
        if ("system" in path.relative_to(TESTS).parts) == system:
            found.append(path.read_text())
    return tuple(found)


def named(name: str, system: bool) -> bool:
    pattern = re.compile(rf"[\"']{re.escape(name)}[\"']|\bc\(\s*[\"']{re.escape(name)}|\bq\(\s*[\"']{re.escape(name)}")
    return any(pattern.search(text) for text in texts(system))


def gaps() -> set[str]:
    """What isn't tested yet, one line each: "<command> regular", "<command> headless", "<feature> web"."""
    out = set()
    for feature in features():
        for name in feature["commands"]:
            if not named(name, system=False):
                out.add(f"{name} regular")
            if not named(name, system=True):
                out.add(f"{name} headless")
        if feature["pages"] and not (E2E / f"{feature['id']}.e2e.mjs").exists():
            out.add(f"{feature['id']} web")
    return out


def listed() -> set[str]:
    if not TODO.exists():
        return set()
    return {line.strip() for line in TODO.read_text().splitlines() if line.strip() and not line.startswith("#")}


def test_every_command_and_query_belongs_to_one_feature() -> None:
    owners: dict[str, list[str]] = {}
    for feature in features():
        for name in feature["commands"]:
            owners.setdefault(name, []).append(feature["id"])
    unowned = sorted(set(REGISTRY) - set(owners))
    assert not unowned, f"commands with no feature in tests/features.toml (add each to one): {unowned}"
    twice = {name: ids for name, ids in owners.items() if len(ids) > 1}
    assert not twice, f"in more than one feature: {twice}"
    gone = sorted(set(owners) - set(REGISTRY))
    assert not gone, f"in tests/features.toml but not a command or query any more (take them out): {gone}"


def test_every_feature_names_a_page_that_exists_or_none() -> None:
    routes = {"/", "/todo", "/projects", "/review", "/inbox", "/inbox/check", "/insights", "/body", "/rules"}
    routes.add("/settings")
    for feature in features():
        for page in feature["pages"]:
            assert page in routes or page.startswith("/settings/"), f"{feature['id']}: no page {page}"


def test_every_layer_tests_every_feature_or_says_its_on_the_way() -> None:
    found, known = gaps(), listed()
    untested = sorted(found - known)
    assert not untested, (
        "not tested in a layer (write the test: TESTING.md; only while building the suite, list it in "
        f"tests/features_todo.txt): {untested}"
    )
    filled = sorted(known - found)
    assert not filled, f"tested now: take these off tests/features_todo.txt: {filled}"
