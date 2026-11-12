"""One version number everywhere (HOSTED.md H174, 8 Nov: Friday was 0.3.0 while the repo said 0.1.0): VERSION, which
the Mac build reads, and the same number in pyproject.toml, web/package.json and
uv.lock files. `scripts/prepare-release.sh` runs it and commits them together; tests/test_versions.py checks they agree.

    python3 scripts/set_version.py 0.4.0
"""

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NUMBER = re.compile(r"\d+\.\d+\.\d+")


def project_version(text: str, value: str) -> str:
    """pyproject.toml's [project] version."""
    return re.sub(r'(?m)(^\[project\][^\[]*?^version = ")[^"]*(")', rf"\g<1>{value}\g<2>", text, count=1)


def locked_version(text: str, name: str, value: str) -> str:
    """uv.lock's own package entry: the one named `name` that is the project itself (editable)."""
    return re.sub(
        rf'(?m)(^name = "{re.escape(name)}"\nversion = ")[^"]*("\nsource = {{ editable = "\." }})',
        rf"\g<1>{value}\g<2>",
        text,
        count=1,
    )


def package_version(text: str, value: str) -> str:
    data = json.loads(text)
    data["version"] = value
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def set_version(root: Path, value: str) -> list[str]:
    """Write `value` into every file that names Friday's version; returns the files, relative to `root`."""
    if not NUMBER.fullmatch(value):
        raise ValueError(f"the version should be a number like 0.4.0, not {value!r}")
    edits = {
        "VERSION": lambda t: value + "\n",
        "pyproject.toml": lambda t: project_version(t, value),
        "web/package.json": lambda t: package_version(t, value),
        "uv.lock": lambda t: locked_version(t, "friday", value),
    }
    # Every file read and changed before any is written: one whose line moved (a `[` before `version` in [project],
    # uv.lock's entry written another way) was written back unchanged, and the release went out mismatched (audit,
    # 12 Nov); a file not there was made empty.
    written = {}
    for name, edit in edits.items():
        path = root / name
        if not path.exists():
            raise FileNotFoundError(f"{name} isn't there: run it from Friday's repo")
        after = edit(path.read_text())
        if not has_version(name, after, value):
            raise ValueError(f"couldn't find Friday's version in {name}: set it there by hand")
        written[path] = after
    for path, after in written.items():
        path.write_text(after)
    return list(edits)


def has_version(name: str, text: str, value: str) -> bool:
    """Whether `text`, the file `name` after the edit, names `value` where Friday's version goes."""
    v = re.escape(value)
    if name == "VERSION":
        return text.strip() == value
    if name == "web/package.json":
        return json.loads(text).get("version") == value
    if name == "pyproject.toml":
        return re.search(rf'(?m)^\[project\][^\[]*?^version = "{v}"', text) is not None
    return re.search(rf'(?m)^name = "friday"\nversion = "{v}"\nsource = {{ editable = "\." }}', text) is not None


if __name__ == "__main__":
    print(" ".join(set_version(REPO, sys.argv[1])))
