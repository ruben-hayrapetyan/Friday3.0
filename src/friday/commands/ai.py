"""Checking the AI (M13): one tiny call to each model Friday uses, so a refused key, a retired model or a request
the model won't take shows here, in plain words, rather than as mail stuck unread."""

from friday.api.types import Empty
from friday.api.views import ModelCheck
from friday.commands.registry import Ctx, query
from friday.ingest import extract, llm

PING = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}


@query("ai_check")
def ai_check(ctx: Ctx, inp: Empty) -> list[ModelCheck]:
    """Ask each model Friday uses for a one-word answer, the way Friday asks; say what came back."""
    client = llm.client()
    budget = ctx.settings["llm"]
    jobs = [(budget.model, "Reads mail and documents"), (budget.small_model, "Sorts what comes in")]
    out = []
    for model, job in jobs:
        if client is None:
            out.append(ModelCheck(model=model, job=job, ok=False, said="No Anthropic API key in secrets.toml"))
            continue
        try:
            found, _ = extract.call(client, model, "Answer ok: true.", [{"type": "text", "text": "Ping"}], PING)
            out.append(ModelCheck(model=model, job=job, ok=found.get("ok") is True, said="Answered"))
        except Exception as error:  # the point is to show it
            out.append(ModelCheck(model=model, job=job, ok=False, said=f"{type(error).__name__}: {error}"[:300]))
    return out
