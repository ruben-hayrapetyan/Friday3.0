"""The planner's compiled code, kept out of the Mac app (HOSTED.md H111, on rhayrapetyan/download-site).

The app ships the planner already compiled (Mac/bundle.sh), but numba files compiled code under the exact macOS
version and the argument types it saw, so a real week, or another Mac, compiles more. Left alone, numba writes that
beside the planner's source, inside the app: 6 Nov, your Friday added 73 files to itself within a minute of opening,
which breaks its signature. So the app sets NUMBA_CACHE_DIR (Server.swift: ~/Library/Caches/Friday/planner) and,
before the first plan, the compiled code it ships is copied there once, where numba then reads and adds to it."""

import hashlib
import importlib.util
import os
import shutil
from pathlib import Path

MARK = "shipped.txt"  # names what was copied, so a new version of the app copies its own


def engine_folder() -> Path:
    """Where the planner's source is, found without importing it (importing compiles nothing, but costs a second)."""
    spec = importlib.util.find_spec("friday.engine")
    assert spec is not None and spec.origin is not None
    return Path(spec.origin).parent


def cache_folder(cache_dir: Path, engine: Path) -> Path:
    """The folder numba reads the planner's compiled code from when NUMBA_CACHE_DIR is set (its own rule)."""
    from numba.core.caching import UserProvidedCacheLocator

    return cache_dir / UserProvidedCacheLocator.get_suitable_cache_subpath(str(engine / "kernel.py"))


def shipped_files(engine: Path) -> list[Path]:
    return sorted((engine / "__pycache__").glob("*.nb[ic]"))


def fingerprint(files: list[Path]) -> str:
    listing = "\n".join(f"{f.name} {f.stat().st_size} {f.stat().st_mtime_ns}" for f in files)
    return hashlib.sha256(listing.encode()).hexdigest()


def seed(cache_dir: str | None = None, engine: Path | None = None) -> Path | None:
    """Copy the compiled planner the app ships to where numba will look, unless it's there already. Nothing when
    NUMBA_CACHE_DIR isn't set (working on Friday, or fridayd installed by deploy.sh: numba's own place is fine)."""
    chosen = cache_dir if cache_dir is not None else os.environ.get("NUMBA_CACHE_DIR")
    if not chosen:
        return None
    engine = engine or engine_folder()
    files = shipped_files(engine)
    target = cache_folder(Path(chosen).expanduser(), engine)
    stamp = fingerprint(files)
    mark = target / MARK
    if mark.exists() and mark.read_text() == stamp:
        return target
    target.mkdir(parents=True, exist_ok=True)
    for found in files:
        shutil.copy2(found, target / found.name)
    mark.write_text(stamp)
    return target
