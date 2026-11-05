"""The fifty test profiles for the hosted Friday (HOSTED.md H73–H76): the seven Cornell students and the forty-three
people of sim/people.py. About half have lived three weeks with Friday (sim/history.py); the rest have just set it
up on their first evening (sim/first_evening.py), the plan made.

`python -m friday.sim.profiles list` names them; `… build DIR [--only KEY …] [--jobs N]` writes each one's data
folder to DIR/KEY (a fresh folder each; an existing one is left alone), which `fridayd --data-dir DIR/KEY demo
--case KEY` then serves with its stand-in Google, Gmail and AI.
"""

import argparse
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from friday.planner.service import replan
from friday.planner.store import kv_set
from friday.sim.cornell import Student
from friday.sim.first_evening import open_student
from friday.sim.history import open_lived_in
from friday.sim.people import KINDS, PEOPLE
from friday.sim.students import STUDENTS

PROFILES: dict[str, Student] = {**STUDENTS, **PEOPLE}
LIVED = frozenset(key for n, key in enumerate(PROFILES) if n % 2 == 1)  # every other one, so each kind has both


def kind_of(key: str) -> str:
    return KINDS.get(key, "student")


def build(folder: Path, key: str, now_utc: int) -> Path:
    """`key`'s data folder as of `now_utc`: lived in, or just set up and planned. Never over an existing one."""
    db_path = folder / "friday.db"
    if db_path.exists():
        raise FileExistsError(f"{db_path} is already there")
    folder.mkdir(parents=True, exist_ok=True)
    os.environ["FRIDAY_CONFIG"] = str(folder / "friday.toml")  # none there: never your config or secrets
    student = PROFILES[key]
    if key in LIVED:
        conn = open_lived_in(db_path, student, now_utc)
    else:
        conn = open_student(db_path, student, now_utc)
        replan(conn, now_utc)
    kv_set(conn, "demo", True)  # said on every page, so the profile isn't taken for anyone's real data
    conn.commit()
    conn.close()
    return db_path


def build_one(args: tuple[Path, str, int]) -> tuple[str, str]:
    """(key, "" or what went wrong): one profile that can't be built is named, and the rest still are."""
    folder, key, now_utc = args
    try:
        build(folder / key, key, now_utc)
    except Exception as e:  # noqa: BLE001  (an error object may not survive the trip back from the worker)
        return key, f"{type(e).__name__}: {e}"
    return key, ""


def line(key: str) -> str:
    s = PROFILES[key]
    return f"{key:10} {kind_of(key):8} {'lived' if key in LIVED else 'fresh':6} {s.name}: {s.about}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m friday.sim.profiles", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="each profile: key, kind, lived or fresh, who they are")
    make = commands.add_parser("build", help="write the profiles' data folders")
    make.add_argument("folder", type=Path)
    make.add_argument("--only", nargs="+", choices=list(PROFILES), metavar="KEY")
    make.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    args = parser.parse_args(argv)
    if args.command == "list":
        print("\n".join(line(key) for key in PROFILES))
        return
    keys = [k for k in (args.only or PROFILES) if not (args.folder / k / "friday.db").exists()]
    now = int(time.time() // 60)  # engine minutes, as the server's clock
    failed = []
    with ProcessPoolExecutor(args.jobs) as pool:
        for key, error in pool.map(build_one, [(args.folder, k, now) for k in keys]):
            print(f"FAILED {key}: {error}" if error else f"built {line(key)}", flush=True)
            failed += [key] if error else []
    print(f"{len(keys) - len(failed)} built in {args.folder}; {len(failed)} failed", file=sys.stderr)
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
