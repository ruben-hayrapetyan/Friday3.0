"""`python -m friday.sim [--weeks 15] [--seed 0] [--days N] [--folder DIR]`: live a simulated term, print metrics."""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from friday.sim.generate import TermConfig
from friday.sim.users import FAMILIES
from friday.sim.world import Metrics, run_term


def progress(day: int, metrics: Metrics) -> None:
    if day % 7 == 0:
        print(f"week {day // 7} lived, {len(metrics.plan_seconds)} replans", file=sys.stderr, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weeks", type=int, default=15)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--days", type=int, help="stop after this many days")
    parser.add_argument("--folder", type=Path, help="keep the database here (a fresh folder) to look at afterwards")
    parser.add_argument("--family", choices=FAMILIES, help="give the student a hidden taste of this kind (learning)")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as scratch:
        folder = args.folder or Path(scratch)
        folder.mkdir(parents=True, exist_ok=True)
        metrics = run_term(folder, TermConfig(weeks=args.weeks), args.seed, args.days, progress, args.family)
    print(json.dumps(metrics.summary(), indent=2))
    for error in metrics.errors[:20]:
        print(error)


if __name__ == "__main__":
    main()
