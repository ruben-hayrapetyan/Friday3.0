"""`fr-serve`: the engine as a long-lived child process of the Friday app, JSON lines over stdin / stdout (PROTOCOL.md).

One request per line: {"id": 1, "method": "plan", "params": {...}}. One reply per line: {"id": 1, "result": ...} or
{"id": 1, "error": {"type": ..., "message": ...}}. The first line written is {"ready": true, ...} once compiled code is
warm. Nothing else is ever written to stdout; diagnostics go to stderr.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback

from .service import OPTION_METHOD, Engine, _now

VERSION = 1


def handle(eng: Engine, method: str, p: dict):
    if method == "hello":
        return dict(protocol=VERSION, data_dir=str(eng.dir))
    if method == "set_estimate":
        return eng.set_estimate(str(p["task_id"]), p["minutes"])
    if method == "record_actual":
        return eng.record_actual(p["task"], p["minutes"])
    if method == "predict":
        return eng.predict(p["todos"], _now(p))
    if method == "questions":
        return eng.questions(p["todos"], _now(p))
    if method == "mark_asked":
        return eng.mark_asked(str(p["task_id"]))
    if method == "parse_constraints":
        return eng.parse_constraints(p["text"], p.get("todos", []), p.get("events", []), _now(p))
    if method == "confirm_constraints":
        return eng.confirm_constraints(p["pending_id"], [int(i) for i in p.get("accept", [])])
    if method == "list_constraints":
        return eng.list_constraints()
    if method == "remove_constraint":
        return eng.remove_constraint(p["id"])
    if method == "plan":
        return eng.plan(p["todos"], p.get("events", []), _now(p), p.get("method", OPTION_METHOD))
    if method == "suggest_skips":
        return eng.suggest_skips(p.get("events", []), _now(p))
    if method == "decide_event":
        return eng.decide_event(p["title"], p["start"], p["decision"])
    if method == "pick":
        return eng.pick(p["plan_id"], int(p["option"]))
    raise ValueError(f"unknown method {method!r}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="fr-serve")
    ap.add_argument("--data", help="state folder (default ~/Library/Application Support/Friday/engine)")
    ap.add_argument("--steps", type=int, default=300_000, help="annealing steps for the recommended plan")
    ap.add_argument("--no-warmup", action="store_true")
    a = ap.parse_args(argv)
    t = time.perf_counter()
    if not a.no_warmup:
        from ..engines.api import warmup
        warmup()
    eng = Engine(a.data, steps=a.steps)
    out = sys.stdout
    out.write(json.dumps(dict(ready=True, protocol=VERSION, warmup_s=round(time.perf_counter() - t, 2))) + "\n")
    out.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            res = handle(eng, req["method"], req.get("params", {}))
            reply = dict(id=rid, result=res)
        except Exception as e:  # noqa: BLE001 - every failure becomes an error reply; the process keeps serving
            traceback.print_exc(file=sys.stderr)
            reply = dict(id=rid, error=dict(type=type(e).__name__, message=str(e)))
        out.write(json.dumps(reply, default=float) + "\n")
        out.flush()


if __name__ == "__main__":
    main()
