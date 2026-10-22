"""Terminal output (DESIGN §19): plain aligned text, colour only for warnings and errors. Ids print as T42 (items),
P7 (plans), C881 (commands) and T42@Tue14:00 (blocks)."""

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from rich.console import Console

out = Console(highlight=False, soft_wrap=True)
err = Console(stderr=True, highlight=False, soft_wrap=True)


def show(name: str, response: Any, as_json: bool) -> None:
    if as_json:
        out.print(json.dumps(response, indent=2), markup=False)
        return
    if isinstance(response, dict) and "command_id" in response and "result" in response:
        lines = command_lines(name, response)
    else:
        lines = RENDERERS.get(name, fallback)(response)
    for line in lines:
        style = "yellow" if line.startswith("! ") else None
        out.print(line, style=style, markup=False)


def error(message: str) -> None:
    err.print(f"friday: {message}", style="red", markup=False)


def command_lines(name: str, response: dict[str, Any]) -> list[str]:
    lines = RENDERERS.get(name, fallback)(response["result"])
    if response.get("preview"):
        lines = ["Preview; nothing changed.", *lines]
    elif response.get("command_id"):
        footer = f"(C{response['command_id']}, undo: friday undo C{response['command_id']})"
        lines = [f"{lines[0]}   {footer}" if lines else footer, *lines[1:]]
    if response.get("repeated"):
        lines.append("(already done earlier with this idempotency key)")
    ghosts = ghost_line(name, response)
    return lines + ghosts


def ghost_line(name: str, response: dict[str, Any]) -> list[str]:
    item = (response["result"] or {}).get("item") if isinstance(response["result"], dict) else None
    if name != "add" or not item or not response.get("provisional"):
        return []
    mine = [span(g["start"], g["end"]) for g in response["provisional"] if g["item_id"] == item["id"]]
    return [f"Probably {', '.join(mine)} (planning…)"] if mine else []


# Times and lengths


def moment(local: str) -> datetime:
    return datetime.fromisoformat(local)


def when(local: str | None) -> str:
    return moment(local).strftime("%a %b %-d %H:%M") if local else ""


def span(start: str, end: str) -> str:
    a, b = moment(start), moment(end)
    return f"{a:%a %H:%M}-{b:%H:%M}" if a.date() == b.date() else f"{a:%a %H:%M}-{b:%a %H:%M}"


def clock(start: str, end: str) -> str:
    return f"{moment(start):%H:%M}-{moment(end):%H:%M}"


def short_key(key: str) -> str:
    item, _, start = key.partition("@")
    try:
        return f"{item}@{moment(start):%a%H:%M}"
    except ValueError:  # already short, as typed
        return key


def length(minutes: int | None) -> str:
    if minutes is None:
        return "open"
    if minutes < 60:
        return f"{minutes} min"
    return f"{minutes / 60:g} h" if minutes % 30 == 0 else f"{minutes // 60}:{minutes % 60:02d} h"


def table(rows: list[list[str]]) -> list[str]:
    widths = [max(len(r[i]) for r in rows) for i in range(len(rows[0]))] if rows else []
    return ["  ".join(c.ljust(w) for c, w in zip(r, widths, strict=True)).rstrip() for r in rows]


def titled(item: dict[str, Any]) -> str:
    return f"{item['title']} · {item['area']}" if item.get("area") else item["title"]


def block_title(block: dict[str, Any]) -> str:
    marks = [block["pinned"]] if block.get("pinned") else []
    marks += ["tentative"] if block.get("tentative") else []
    return block["title"] + (f"  [{', '.join(marks)}]" if marks else "")


# One renderer per verb that has more to say than its message


def fallback(result: Any) -> list[str]:
    if isinstance(result, dict) and set(result) <= {"message"}:
        return [result.get("message", "Done")]
    if isinstance(result, dict) and "message" in result and result["message"]:
        return [result["message"]]
    return json.dumps(result, indent=2).splitlines()


def item_row(item: dict[str, Any]) -> list[str]:
    if item["when"] == "fixed":
        left, due = span(item["start"], item["end"]) if item["start"] else "", ""
    else:
        left = length(item["remaining_min"])
        due = f"due {when(item['due'])}" if item.get("due") else ""
    status = "" if item["status"] == "todo" else item["status"]
    if item["status"] == "todo" and item["remaining_min"] == 0:
        status = "finished?"
    return [f"T{item['id']}", titled(item), left, due, status]


def added(result: dict[str, Any]) -> list[str]:
    lines = []
    if result.get("item"):
        item = result["item"]
        lines.append(f"Added T{item['id']}  " + "   ".join(c for c in item_row(item)[1:4] if c))
    if result.get("series_id"):
        lines.append(f"Repeats as S{result['series_id']}: {result['occurrences']} occurrences so far")
    return lines + [f"! {w}" for w in result.get("warnings", [])]


def one_item(result: dict[str, Any]) -> list[str]:
    return table([item_row(result["item"])])


def items(result: list[dict[str, Any]]) -> list[str]:
    return table([item_row(i) for i in result]) or ["Nothing here."]


def item_detail(result: dict[str, Any]) -> list[str]:
    item = result["item"]
    lines = table([item_row(item)])
    lines += [f"  planned  {span(b['start'], b['end'])}   {short_key(b['key'])}" for b in result["blocks"]]
    lines += [f"  done     {length(p['minutes'])} ({p['source']})" for p in result["progress"]]
    lines += [f"  after    T{d['depends_on_id']}" for d in result["depends_on"]]
    return lines


def plan(result: dict[str, Any]) -> list[str]:
    entries = [(b["start"], b["end"], f"{block_title(b)}   {short_key(b['key'])}") for b in result["blocks"]]
    entries += [(f["start"], f["end"], f"{f['title']}  (fixed)") for f in result["fixed"] if f["start"]]
    if not entries:
        return ["No plan yet." if result["plan_id"] is None else "Nothing planned."]
    lines, day = [], None
    for start, end, text in sorted(entries):
        if start[:10] != day:
            day = start[:10]
            hours = result["day_hours"].get(day)
            lines.append(f"{moment(start):%a %b %-d}" + (f"   {hours:g} h" if hours else ""))
        lines.append(f"  {clock(start, end)}  {text}")
    header = f"Plan P{result['plan_id']}" + (" (provisional)" if result.get("provisional") else "")
    return [header, *lines]


def now(result: dict[str, Any]) -> list[str]:
    rows = []
    if result["current"]:
        c = result["current"]
        left = (moment(c["end"]) - datetime.now()).total_seconds() // 60
        rows.append(["Now", c["title"], clock(c["start"], c["end"]), f"{int(left) // 60}:{int(left) % 60:02d} left"])
    elif result["gap_minutes"]:
        rows.append(["Now", "free", length(result["gap_minutes"]), ""])
    if result["next"]:
        n = result["next"]
        rows.append(["Next", n["title"], clock(n["start"], n["end"]), ""])
    lines = table(rows) if rows else ["Nothing planned."]
    if result["swaps"]:
        lines.append("Safe to switch to:  " + " · ".join(s["title"] for s in result["swaps"]))
    for alert in result["alerts"]:
        lines.append(f"! Start by {moment(alert['latest_start']):%a %H:%M}:  {alert['title']} ({alert['kind']})")
    if result["fits"] and not result["current"]:
        lines.append("Fits this gap:  " + " · ".join(f"{s['title']} ({length(s['minutes'])})" for s in result["fits"]))
    return lines


def why(result: dict[str, Any]) -> list[str]:
    rows = [[f"  {name}", f"{cost / 100:.1f}"] for name, cost in sorted(result["costs"].items(), key=lambda c: -c[1])]
    rows.append(["  total", f"{result['total'] / 100:.1f}"])
    return [short_key(result["key"]), result["sentence"], *table(rows)]


def why_not(result: dict[str, Any]) -> list[str]:
    target = f" to {when(result['to_start'])}" if result.get("to_start") else ""
    if result.get("wall"):
        return [f"Can't move {short_key(result['key'])}{target}: {result['wall']}"]
    changed = sorted((c for c in result["difference"].items() if c[1]), key=lambda c: -abs(c[1]))
    rows = [[f"  {name}", f"{cost / 100:+.1f}"] for name, cost in changed]
    return [f"Moving {short_key(result['key'])}{target} costs {result['total'] / 100:+.1f}", *table(rows)]


def changes(result: dict[str, Any]) -> list[str]:
    lines = [f"Added    {b['title']}  {span(b['start'], b['end'])}" for b in result["added"]]
    for m in result["moved"]:
        before = ", ".join(span(a, b) for a, b in m["before"])
        after = ", ".join(span(a, b) for a, b in m["after"])
        lines.append(f"Moved    {m['title']}  {before} -> {after}")
    lines += [f"Removed  {b['title']}  {span(b['start'], b['end'])}" for b in result["removed"]]
    lines += [
        f"  because C{i['command_id']} {i['actor']} {i['command']}" for i in result["inputs"] if "command_id" in i
    ]
    return (lines or ["No changes."]) + [f"! {n}" for n in result["notices"]]


def triage(result: dict[str, Any]) -> list[str]:
    if not result["late"]:
        return ["Nothing is late."]
    lines = [f"! {title}: {hours:g} h late" for title, hours in result["late"].items()]
    rows = [
        [o["action"], f"saves {o['late_hours_saved']:g} h", "; ".join(o["side_effects"])] for o in result["options"]
    ]
    return lines + table(rows)


def review(result: dict[str, Any]) -> list[str]:
    lines = [f"Review of {result['date']}" + (" (done)" if result["reviewed"] else "")]
    lines += [f"  {clock(b['start'], b['end'])}  {b['title']}   {short_key(b['key'])}" for b in result["blocks"]]
    lines += [f"  finished?  T{i['id']} {i['title']}  (friday done T{i['id']})" for i in result["finished"]]
    return lines


def paces(result: dict[str, Any]) -> list[str]:
    rows = [
        ["Default" if name == result["default"] else "", name, *(f"{d.get(k, 0):g}" for k in DIALS)]
        for name, d in result["paces"].items()
    ]
    until = f" through {result['period_end']}" if result.get("period_end") else ""
    return [*table([["", "", *DIALS], *rows]), f"Now: {result['now_label']}{until}"]


def status(result: dict[str, Any]) -> list[str]:
    plan_text = f"Plan P{result['plan_id']}" if result["plan_id"] else "No plan yet"
    behind = result["plan_generation"] is not None and result["plan_generation"] < result["generation"]
    lines = [plan_text + (" (replanning…)" if behind else "")]
    if result["timer"]:
        lines.append(f"Timer on T{result['timer']['item_id']} for {length(result['timer']['minutes'])}")
    if not result["ready"]:
        lines.append("! Not set up yet: run `fridayd init`")
    return lines + [f"! {p}" for p in result["problems"] + result["notices"]]


def diagnose(result: list[dict[str, Any]]) -> list[str]:
    rows = [[when(h["at"]), h["kind"], h["summary"]] for h in result]
    return table(rows) or ["Nothing in that stretch."]


def log_list(result: list[dict[str, Any]]) -> list[str]:
    rows = [
        [f"C{e['id']}", when(e["at"]), e["actor"], e["command"], given(e["input"])[:60],
         f"undone by C{e['undone_by']}" if e["undone_by"] else ""]
        for e in result
    ]  # fmt: skip
    return table(rows) or ["No commands yet."]


def given(fields: dict[str, Any]) -> str:
    return " ".join(f"{k}={json.dumps(v)}" for k, v in fields.items() if v not in (None, [], {}))


def shove(result: dict[str, Any]) -> list[str]:
    lines = [result["message"]] if result["message"] else []
    for m in result["must_do"]:
        lines.append(f"! {m['title']}: {m['extra_late_hours']:g} h later ({m['planned_hours_in_range']:g} h planned)")
    if result["must_do"]:
        lines.append("Send it again with --decision shove_anyway, keep_must_dos or cancel.")
    return lines or ["Done"]


def fits(result: list[dict[str, Any]]) -> list[str]:
    return table([[f"T{s['item_id']}", s["title"], length(s["minutes"])] for s in result]) or ["Nothing fits."]


def totals(result: dict[str, int]) -> list[str]:
    return table([[name, f"{cost / 100:.1f}"] for name, cost in sorted(result.items(), key=lambda c: -c[1])])


STATUS = {"done": "done", "on_track": "on track", "late": "LATE", "unplanned": "not planned"}


def projects(result: list[dict[str, Any]]) -> list[str]:
    lines = []
    for p in result:
        item, finish = p["item"], p["planned_finish"]
        lines.append(
            f"T{item['id']}  {titled(item)}  due {when(item['due']) or '-'}  {length(p['done_min'])} done, "
            f"{length(p['remaining_min'])} left  {STATUS[p['status']]}"
            + (f", finishes {finish[:16]}" if finish else "")
        )
        lines += [f"  T{c['id']}  {c['title']}  {length(c['remaining_min'] or 0)} left" for c in p["children"]]
    return lines or ["No projects."]


def load(result: list[dict[str, Any]]) -> list[str]:
    rows = [
        [w["start"], f"{w['hours']:g} / {w['capacity']:g} h", "forecast" if w["forecast"] else "planned",
         ", ".join(d["title"] for d in w["due"])]
        for w in result
    ]  # fmt: skip
    return table(rows)


DIALS = ("capacity", "rest", "spread", "growth")
RENDERERS: dict[str, Callable[[Any], list[str]]] = {
    "add": added,
    "edit": one_item,
    "done": one_item,
    "drop": one_item,
    "reopen": one_item,
    "progress": one_item,
    "skip": one_item,
    "log": one_item,
    "items": items,
    "item": item_detail,
    "plan": plan,
    "now": now,
    "why": why,
    "why_not": why_not,
    "changes": changes,
    "preview_weights": changes,
    "triage": triage,
    "review": review,
    "paces": paces,
    "status": status,
    "log_list": log_list,
    "diagnose": diagnose,
    "shove": shove,
    "fits": fits,
    "rule_totals": totals,
    "projects": projects,
    "load": load,
    "template_apply": one_item,
}
