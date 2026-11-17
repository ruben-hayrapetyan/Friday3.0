"""A project's own options, set on its page: its pace through the work (front-loaded, even, toward the end, or its
kind's), followed by its steps when planning (planner/ongoing.py `project_pacing`); and finishing it some days early,
a rule of yours about this project alone (scope `project`), listed in Rules with the others ("Finish History essay
3 days early"), where its strength can change or it can be switched off. 0 days takes the rule away."""

import json

from friday.api.commands import Changed, ProjectSetInput
from friday.api.types import Empty
from friday.api.views import ProjectOptionsOut
from friday.commands.archive import require_project
from friday.commands.registry import Ctx, command, query
from friday.commands.settings import write_setting
from friday.core.items import FieldError
from friday.core.time import parse_utc
from friday.planner.ongoing import PACINGS, PROJECT_OPTIONS
from friday.planner.store import kv_get

PACE_WORDS = {"front": "most of it early", "linear": "spread evenly to its due", "back": "most of it toward its due"}


def early_rule(project_id: int) -> str:
    return f"you:project:{project_id}:early"


def days_words(days: float) -> str:
    return f"{days:g} {'day' if days == 1 else 'days'}"


def options(ctx: Ctx) -> dict[str, dict]:
    return dict(kv_get(ctx.conn, PROJECT_OPTIONS, {}, ctx.user_id) or {})


@command("project_set", affects_plan=True)
def project_set(ctx: Ctx, inp: ProjectSetInput) -> Changed:
    """Set a project's pace through its work ("kind": its kind's) or how many days early to finish it (0: none)."""
    title = require_project(ctx, inp.id)
    said = []
    if inp.pacing is not None:
        saved = options(ctx)
        mine = dict(saved.get(str(inp.id), {}))
        mine["pacing"] = inp.pacing if inp.pacing in PACINGS else None
        saved[str(inp.id)] = mine
        ctx.db.upsert("kv", {"user_id": ctx.user_id, "key": PROJECT_OPTIONS}, {"value": json.dumps(saved)})
        said.append(PACE_WORDS.get(inp.pacing, "as its kind is paced"))
    if inp.early_days is not None:
        due = ctx.conn.execute("SELECT due_utc FROM items WHERE id = ?", [inp.id]).fetchone()[0]
        left = (parse_utc(due) - ctx.now_utc) / 1440 if due else None
        if inp.early_days and left is not None and inp.early_days >= left:
            raise FieldError("early_days", f"it's due in {max(0, int(left))} days: finish early by fewer than that")
        set_early(ctx, inp.id, title, inp.early_days)
        days = inp.early_days
        said.append(f"aims to finish {days_words(days)} early" if days else "no aim to finish early")
    return Changed(message=f"{title}: {', '.join(said)}" if said else "Nothing changed")


def set_early(ctx: Ctx, project_id: int, title: str, days: float) -> None:
    name = early_rule(project_id)
    rules = [r.model_dump() for r in ctx.settings["rules"] if r.name != name]
    if days:
        rules.append(
            {
                "type": "finish_early",
                "name": name,
                "weight": 1.0,  # Prefer, as a rule you add is to start; Rules makes it stronger
                "stage": None,
                "scope": {"project": [str(project_id)]},
                "params": {"days": days},
                "enabled": True,
                "reason": f"Finish {title} {days_words(days)} early",
            }
        )
    write_setting(ctx, "rules", rules)


def rules_of(ctx: Ctx, project_id: int) -> list[dict]:
    """The rules about this project alone."""
    return [r.model_dump() for r in ctx.settings["rules"] if r.name.startswith(f"you:project:{project_id}:")]


def put_rules_away(ctx: Ctx, project_id: int) -> list[dict]:
    """Its own rules taken out of Rules (archiving: a finished project needs none), returned to keep."""
    away = rules_of(ctx, project_id)
    if away:
        names = {r["name"] for r in away}
        write_setting(ctx, "rules", [r.model_dump() for r in ctx.settings["rules"] if r.name not in names])
    return away


def bring_rules_back(ctx: Ctx, kept: list[dict]) -> None:
    if kept:
        names = {r["name"] for r in kept}
        write_setting(ctx, "rules", [*(r.model_dump() for r in ctx.settings["rules"] if r.name not in names), *kept])


@query("project_options")
def project_options(ctx: Ctx, inp: Empty) -> list[ProjectOptionsOut]:
    """Each project's own options that are set: its pace through the work and how many days early it aims to finish."""
    saved = options(ctx)
    early = {
        int(r.name.split(":")[2]): float(r.params.get("days", 0))
        for r in ctx.settings["rules"]
        if r.name.startswith("you:project:") and r.name.endswith(":early") and r.enabled
    }
    ids = sorted({int(k) for k, v in saved.items() if v.get("pacing")} | set(early))
    return [
        ProjectOptionsOut(id=i, pacing=saved.get(str(i), {}).get("pacing"), early_days=early.get(i, 0)) for i in ids
    ]
