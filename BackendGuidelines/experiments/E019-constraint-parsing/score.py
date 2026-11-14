"""Scoring a parse against the hand-labeled cases in gold.py (rules in gold.py's docstring)."""
from __future__ import annotations

import itertools
from types import SimpleNamespace

from fr.product.constraints import Parse, Target

from gold import CONTEXT

TASKS = [SimpleNamespace(title=t["title"], area=t["course"], preset=t["kind"], energy=t["energy"]) for t in CONTEXT["tasks"]]
ALL7 = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
SOFT = {"strong", "medium", "mild"}
NUMERIC = {"hours", "min_hours", "max_hours", "before_min", "after_min"}


def _opts(v):
    return list(v) if isinstance(v, tuple) else [v]


def _days(v):
    return None if v is None or set(v) == ALL7 else frozenset(v)


def _clock(v, field):
    if field in ("start",) and v in (None, "00:00"):
        return "00:00"
    if field == "end" and v in (None, "00:00", "24:00"):
        return "24:00"
    return v


def selected(target: dict | None) -> frozenset[str]:
    t = Target(**(target or {}))
    return frozenset(x.title for x in TASKS if t.matches(x))


def _titles(sub: str) -> frozenset[str]:
    return frozenset(x.title for x in TASKS if sub.lower() in x.title.lower())


def _number_ok(want, g) -> bool:
    return g is not None and any(abs(float(g) - w) <= max(0.01, 0.03 * abs(w)) for w in _opts(want))


def field_ok(kind: str, field: str, want, got: dict) -> bool:
    g = got.get(field)
    if field in NUMERIC or (field == "days" and kind == "finish_early"):
        return _number_ok(want, g)
    if field in ("days", "nights"):
        return _days(want) == _days(g)
    if field in ("start", "end", "bedtime", "wake"):
        return any(_clock(w, field) == _clock(g, field) for w in _opts(want))
    if field == "strength":
        return any((g in SOFT) if w == "soft" else g == w for w in _opts(want))
    if field == "target":
        return selected(want) == selected(g)
    if field == "dates":
        return set(want) == set(g or [])
    if field in ("first", "then"):
        return g is not None and _titles(want) == _titles(g) and len(_titles(g)) == 1
    return any(g == w for w in _opts(want))


def matches(want: dict, got: dict) -> list[str]:
    """Fields of `want` that `got` gets wrong (empty = a match). A different kind is a mismatch on 'kind'."""
    if want["kind"] != got.get("kind"):
        return ["kind"]
    return [f for f, w in want.items() if f != "kind" and not field_ok(want["kind"], f, w, got)]


def best_matching(want: list[dict], got: list[dict]) -> tuple[int, list[list[str]]]:
    """Largest number of exact 1-1 matches; for unmatched wanted constraints, the fields wrong in the closest guess."""
    n, m = len(want), len(got)
    if n == 0:
        return 0, []
    best, best_perm = -1, None
    idx = list(range(m)) + [None] * n
    for perm in set(itertools.permutations(idx, n)):
        k = sum(1 for i, j in enumerate(perm) if j is not None and not matches(want[i], got[j]))
        if k > best:
            best, best_perm = k, perm
    misses = []
    for i, j in enumerate(best_perm):
        if j is None or matches(want[i], got[j]):
            cands = [matches(want[i], g) for g in got if g.get("kind") == want[i]["kind"]]
            misses.append(min(cands, key=len) if cands else ["missing"])
    return best, misses


def score(case: dict, parse: Parse | None) -> dict:
    if parse is None:
        return dict(id=case["id"], tag=case["tag"], split=case["split"], valid=False, correct=False, cons_ok=False,
                    ask_ok=False, unsup_ok=False, n_want=len(case["want"]), n_got=0, matched=0, extra=0, asked=False,
                    flagged=False, wrong_fields="invalid")
    got = [c.model_dump() for c in parse.constraints]
    asked, flagged = bool(parse.questions), bool(parse.unsupported)
    readings = [case["want"]] + case["alts"]
    results = []
    for want in readings:
        k, misses = best_matching(want, got)
        results.append((k == len(want) and len(got) == k, k, len(got) - k, misses, want))
    results.sort(key=lambda r: (not r[0], -(r[1] - r[2])))
    cons_ok, k, extra, misses, want = results[0]
    if case["ask"] == "must" and not case["want"]:
        cons_ok = cons_ok or (asked and extra == 0)
    if case["ask"] == "ok" and asked and not got:  # "a question or one of the readings is fine"
        cons_ok = True
    ask_ok = {"must": asked, "no": not asked, "ok": True}[case["ask"]]
    if case["unsup"]:
        unsup_ok = flagged or (asked and case["ask"] != "no") or (cons_ok and any(r[0] for r in results[1:]))
    else:
        unsup_ok = not flagged
    return dict(id=case["id"], tag=case["tag"], split=case["split"], valid=True, correct=cons_ok and ask_ok and unsup_ok,
                cons_ok=cons_ok, ask_ok=ask_ok, unsup_ok=unsup_ok, n_want=len(want), n_got=len(got), matched=k,
                extra=extra, asked=asked, flagged=flagged,
                wrong_fields=";".join(",".join(m) for m in misses))


def as_prediction(case: dict) -> Parse:
    """The gold reading itself as a reply (first option of every choice); used to check the scorer."""
    cons = []
    for w in case["want"]:
        d = {k: (v[0] if isinstance(v, tuple) else v) for k, v in w.items()}
        if d["kind"] == "avoid_time" and "strength" in d and d["strength"] == "soft":
            d["strength"] = "medium"
        if d.get("strength") == "soft":
            d["strength"] = "medium"
        if d["kind"] == "commitment":
            d.setdefault("title", "x")
            d.setdefault("start", "09:00")
            d.setdefault("end", "10:00")
        if d["kind"] == "keep_free":
            d.setdefault("hours", 2)
        if d["kind"] == "pacing":
            d.setdefault("style", "spread")
        if d["kind"] == "daily_limit":
            d.setdefault("hours", 4)
        if d["kind"] == "finish_early":
            d.setdefault("days", 1)
        if d["kind"] == "buffer":
            d.setdefault("event_kind", "class")
        cons.append(d)
    q = ["?"] if case["ask"] == "must" else []
    u = [{"source": case["text"], "reason": "x"}] if case["unsup"] and case["ask"] != "must" else []
    return Parse.model_validate(dict(constraints=cons, questions=q, unsupported=u))
