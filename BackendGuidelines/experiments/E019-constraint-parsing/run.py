"""E019: plain-language constraints -> typed constraints with Sonnet 5.5 (RQ16).

Usage:
  uv run python experiments/E019-constraint-parsing/run.py selfcheck
  uv run python experiments/E019-constraint-parsing/run.py run <round>      # variants and split from config.toml
  uv run python experiments/E019-constraint-parsing/run.py report
Replies are cached in results/raw/<variant>/<case>-r<rep>.json, so a rerun only calls Claude for what is missing.
"""
from __future__ import annotations

import json
import sys
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from fr.core.generate import cornell_semester  # noqa: E402
from fr.product import constraints as C  # noqa: E402
from fr.product.parse import Prompt, parse_text  # noqa: E402

from gold import CASES, CONTEXT  # noqa: E402
from score import as_prediction, score  # noqa: E402

RES = HERE / "results"
CFG = tomllib.loads((HERE / "config.toml").read_text())


def examples(ids: list[int]) -> list[dict]:
    """Few-shot examples from tuning cases: the gold reading rendered as a reply."""
    out = []
    for i in ids:
        case = CASES[i]
        assert case["split"] == "tune", "examples must come from the tuning split"
        reply = json.loads(as_prediction(case).model_dump_json(exclude_defaults=True))
        out.append(dict(text=case["text"], reply=reply))
    return out


def prompt(name: str) -> Prompt:
    v = CFG["variants"][name]
    return Prompt(name, guide=v.get("guide", True), examples=examples(v.get("examples", [])),
                  enforce_schema=v.get("enforce_schema", True), retries=v.get("retries", 1))


def one(variant: str, case: dict, rep: int) -> dict:
    path = RES / "raw" / variant / f"{case['id']:03d}-r{rep}.json"
    if path.exists():
        return json.loads(path.read_text())
    try:
        r = parse_text(case["text"], CONTEXT, prompt(variant))
        rec = dict(raw=r.raw, parse=r.parse.model_dump(mode="json") if r.parse else None, error=r.error, cost=r.cost,
                   seconds=r.seconds, calls=r.calls)
    except Exception as e:  # noqa: BLE001 - a failed call is a result, recorded and retried on the next run
        return dict(raw=None, parse=None, error=f"call failed: {e}", cost=0.0, seconds=0.0, calls=0, transient=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=1))
    return rec


def compiles(parse: C.Parse) -> bool:
    try:
        C.apply(cornell_semester(0), parse.constraints)
        return True
    except Exception:  # noqa: BLE001
        return False


def rows(variant: str, split: str, reps: int) -> list[dict]:
    cases = [c for c in CASES if split == "all" or c["split"] == split]
    jobs = [(c, r) for c in cases for r in range(reps)]
    with ThreadPoolExecutor(CFG["workers"]) as ex:
        recs = list(ex.map(lambda cr: one(variant, *cr), jobs))
    out = []
    for (case, rep), rec in zip(jobs, recs):
        parse = C.Parse.model_validate(rec["parse"]) if rec["parse"] else None
        s = score(case, parse)
        s.update(variant=variant, rep=rep, cost=rec["cost"], seconds=rec["seconds"], calls=rec["calls"],
                 compiles=compiles(parse) if parse else False, error=(rec["error"] or "")[:200])
        out.append(s)
    return out


def selfcheck() -> None:
    bad = [c["id"] for c in CASES if not score(c, as_prediction(c))["correct"]]
    print(f"{len(CASES)} cases ({sum(c['split'] == 'test' for c in CASES)} held out); gold scored wrong: {bad}")
    assert not bad


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["round", "variant", "split"])
    return g.agg(n=("correct", "size"), correct=("correct", "mean"), cons_ok=("cons_ok", "mean"),
                 ask_ok=("ask_ok", "mean"), unsup_ok=("unsup_ok", "mean"), valid=("valid", "mean"),
                 compiles=("compiles", "mean"), extra=("extra", "sum"), cost=("cost", "sum"),
                 sec=("seconds", "median")).round(3)


def main() -> None:
    cmd = sys.argv[1]
    if cmd == "selfcheck":
        selfcheck()
        return
    if cmd == "run":
        rnd = sys.argv[2]
        spec = CFG["rounds"][rnd]
        allrows = []
        for v in spec["variants"]:
            r = rows(v, spec["split"], spec.get("reps", 1))
            for x in r:
                x["round"] = rnd
            allrows += r
            d = pd.DataFrame(r)
            print(v, f"correct {d.correct.mean():.3f}  cost ${d.cost.sum():.2f}  failed calls {(d.error.str.startswith('call failed')).sum()}",
                  flush=True)
        RES.mkdir(exist_ok=True)
        pd.DataFrame(allrows).to_csv(RES / f"cases_{rnd}.csv", index=False)
    if cmd in ("run", "report"):
        df = pd.concat([pd.read_csv(f) for f in sorted(RES.glob("cases_*.csv"))])
        summ = summarize(df)
        summ.to_csv(RES / "summary.csv")
        print(summ.to_string())


if __name__ == "__main__":
    main()
