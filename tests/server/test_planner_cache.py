"""The planner's compiled code kept out of the Mac app (server/planner_cache.py). Glass box: what `seed` copies,
where, and when it copies again. Black box with numba itself: a function compiled beside its source and seeded is
read from the cache folder without compiling, and what is compiled later goes there, never beside the source."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from friday.server import planner_cache

SOURCE = "from numba import njit\n\n\n@njit(cache=True)\ndef double(x):\n    return x * 2\n"


def shipped(engine: Path, *names: str) -> None:
    (engine / "__pycache__").mkdir(parents=True)
    for name in names:
        (engine / "__pycache__" / name).write_text(name)


def test_without_numba_cache_dir_nothing_is_copied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NUMBA_CACHE_DIR", raising=False)
    shipped(tmp_path / "engine", "kernel.f-1.py312.nbi")
    assert planner_cache.seed(engine=tmp_path / "engine") is None


def test_the_compiled_planner_is_copied_where_numba_looks_and_nothing_else(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    shipped(engine, "kernel.f-1.py312.nbi", "kernel.f-1.py312.1.nbc", "kernel.cpython-312.pyc")
    target = planner_cache.seed(str(tmp_path / "cache"), engine)
    assert target == planner_cache.cache_folder(tmp_path / "cache", engine) and target.parent == tmp_path / "cache"
    assert sorted(p.name for p in target.iterdir()) == ["kernel.f-1.py312.1.nbc", "kernel.f-1.py312.nbi", "shipped.txt"]


def test_it_copies_once_and_again_only_when_the_app_ships_different_code(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    shipped(engine, "kernel.f-1.py312.nbi")
    target = planner_cache.seed(str(tmp_path / "cache"), engine)
    assert target is not None
    (target / "kernel.f-1.py312.nbi").write_text("grown here: more compiled since")
    planner_cache.seed(str(tmp_path / "cache"), engine)
    assert (target / "kernel.f-1.py312.nbi").read_text() == "grown here: more compiled since"
    (engine / "__pycache__" / "kernel.f-1.py312.nbi").write_text("a new version's")
    planner_cache.seed(str(tmp_path / "cache"), engine)
    assert (target / "kernel.f-1.py312.nbi").read_text() == "a new version's"


def run(folder: Path, code: str, cache: Path | None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "NUMBA_CACHE_DIR"}
    if cache is not None:
        env["NUMBA_CACHE_DIR"] = str(cache)
    done = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, {str(folder)!r}); import planned; {code}"],
        env=env, capture_output=True, text=True, timeout=120, check=True,
    )  # fmt: skip
    return done.stdout.strip()


def test_numba_reads_the_seeded_code_and_compiles_more_only_into_the_cache(tmp_path: Path) -> None:
    folder = tmp_path / "app" / "engine"
    folder.mkdir(parents=True)
    (folder / "planned.py").write_text(SOURCE)
    run(folder, "planned.double(2)", cache=None)  # the build: compiled beside the source
    built = sorted(p.name for p in (folder / "__pycache__").iterdir())
    cache = tmp_path / "Caches" / "planner"
    planner_cache.seed(str(cache), folder)
    hits = run(folder, "planned.double(2); print(dict(planned.double.stats.cache_hits))", cache)
    assert hits != "{}", "the seeded code wasn't used: numba compiled again"
    run(folder, "planned.double(2.5)", cache)  # a new argument type: compiled now
    assert sorted(p.name for p in (folder / "__pycache__").iterdir()) == built  # nothing added beside the source
    added = [p.name for p in planner_cache.cache_folder(cache, folder).iterdir() if p.suffix == ".nbc"]
    assert len(added) == 2, added


def test_the_planners_source_is_found_without_importing_it() -> None:
    folder = planner_cache.engine_folder()
    assert folder.name == "engine" and (folder / "kernel.py").exists() and folder.parent.name == "friday"
