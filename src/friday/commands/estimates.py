"""Learned durations for new items (DESIGN §21.7), kept apart from the nightly fit in `learned.py` so that
`add` can use them without importing the review machinery."""

from typing import Any

from friday.commands.registry import Ctx
from friday.core.textnorm import norm, similarity, type_text
from friday.learn.durations import Model
from friday.planner.store import kv_get


def in_use(settings: dict[str, Any], kept: dict[str, Any] | None, module: str) -> bool:
    """In auto mode (learned lengths only once they predict better), or once you approved it in suggest mode."""
    mode = getattr(settings["learn"], module)
    if not kept or mode == "off":
        return False
    if mode == "auto":
        return module != "durations" or bool(kept.get("better"))
    return bool(kept.get("approved"))


def learned_minutes(ctx: Ctx, title: str, area: str | None, preset: str | None, hard: bool) -> tuple[int, dict] | None:
    """A new item's length from learned durations, when they are in use: p80 for hard-deadline work, else p50."""
    kept = kv_get(ctx.conn, "learned_durations", None, ctx.user_id)
    if not in_use(ctx.settings, kept, "durations"):
        return None
    model = Model.from_json(kept["model"])
    rules = ctx.settings["text"].rules()
    words = type_text(norm(title, rules, area))
    known = list(model.counts.get("kind", {}))
    kind = next((k for k in known if similarity(words, k.split()) >= ctx.settings["estimate"].min_similarity), None)
    p50, p80 = model.minutes(area, preset, kind, False), model.minutes(area, preset, kind, True)
    detail = {
        "method": "learned",
        "p50_min": round(p50),
        "p80_min": round(p80),
        "kind": kind,
        "kind_done": model.counts.get("kind", {}).get(kind or "", 0),
        "area": area,
    }
    return round(p80 if hard else p50), detail
