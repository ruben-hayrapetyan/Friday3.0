"""E018b: the fixed v3 pipeline on E018's instances. Usage: uv run python run.py [--smoke] (from this folder)."""
from __future__ import annotations

import csv
import importlib.util
import sys
import tomllib
from pathlib import Path

from fr.bench import update_best
from fr.core.evaluate import check, evaluate
from fr.engines.api import run_v3, warmup
from fr.engines.prepare import prepare

HERE = Path(__file__).parent
cfg = tomllib.loads((HERE / "config.toml").read_text())
spec = importlib.util.spec_from_file_location("e018", HERE.parent / "E018-weakness-hunt" / "run.py")
sys.argv, argv = [sys.argv[0]], sys.argv  # E018's module reads sys.argv at import
e018 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e018)
sys.argv = argv
if "--smoke" in sys.argv:
    cfg.update(seeds=[0])
    HERE = HERE / "smoke"
    HERE.mkdir(exist_ok=True)
(HERE / "results").mkdir(exist_ok=True)
LOG = (HERE / "progress.txt").open("a")


def log(m: str) -> None:
    print(m, flush=True)
    LOG.write(m + "\n")
    LOG.flush()


def main() -> None:
    warmup()
    rows = []
    for fam, make in e018.FAMILIES.items():
        for seed in cfg["seeds"]:
            sc = make(seed)
            p = sc.build()
            pr = prepare(p)
            res = run_v3(p, pr, cfg["budget_s"], seed)
            v = check(p, res.plan)
            ev = evaluate(p, res.plan)
            if not v:
                update_best(sc.name, ev.lex(), "E018b/v3_fixed")
            rows.append(dict(family=fam, instance=sc.name, seed=seed, engine="v3_fixed", items=len(p.items),
                             seconds=round(res.seconds, 2), violations=len(v), late=ev.stage_values["deadlines"],
                             wellbeing=ev.stage_values["wellbeing"], preferences=ev.stage_values["preferences"],
                             misses=len(ev.deadline_misses), **{k: str(x) for k, x in res.info.items()
                                                                if k in ("repair_late", "after_sampler_late", "fallback")}))
            log(f"{sc.name} v3_fixed lex={ev.lex()} viol={len(v)} {res.seconds:.1f}s {res.info.get('fallback')}")
            with (HERE / "results" / "runs.csv").open("w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=sorted({k for r in rows for k in r}))
                w.writeheader()
                w.writerows(rows)
    log("done")


if __name__ == "__main__":
    main()
