"""The live check (PROGRESS.md C96): an integration's connector against the real service, before a release, so the fake
the tests use (tests/integrations/fake_*.py) can't drift from what the service really does.

    uv run python scripts/live-check.py todoist
    uv run python scripts/live-check.py notion        (asana, linear, jira, github, canvas: read only)

The token is read from your Keychain by name (`security add-generic-password -s friday-live-todoist -a friday -w`
stores it; this script never prints it), or from FRIDAY_LIVE_TOKEN. Everything happens in a project of its own,
"Friday live check", which it makes if it has to: a task is added there, read through Friday's connector, marked done
and opened again through it, then deleted. Your other projects are only read, never changed. At the end it compares
the shape of the real answers (their fields and types) with the fake's, and says what differs.

Exit 0: all of it worked and the fake matches. Exit 1: a step failed or the shapes differ (said above it)."""

import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from friday.integrations.base import ConnectorError, Http  # noqa: E402
from friday.integrations.todoist import API, Todoist  # noqa: E402

PROJECT = "Friday live check"


def token(kind: str) -> str:
    if found := os.environ.get("FRIDAY_LIVE_TOKEN"):
        return found
    said = subprocess.run(["security", "find-generic-password", "-s", f"friday-live-{kind}", "-w"],
                          capture_output=True, text=True)  # fmt: skip
    if said.returncode != 0:
        sys.exit(f"No token: store one with `security add-generic-password -s friday-live-{kind} -a friday -w`")
    return said.stdout.strip()


def shape(value: Any) -> Any:
    """A JSON answer's fields and types, its values gone: what the fake must match."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def differences(real: Any, fake: Any, path: str = "") -> list[str]:
    """Where the fake's shape differs from the real one's (a field missing or of another type)."""
    out: list[str] = []
    if isinstance(real, dict) and isinstance(fake, dict):
        for k in sorted(set(real) | set(fake)):
            if k not in fake:
                out.append(f"{path}.{k}: the real answer has it, the fake doesn't")
            elif k not in real:
                out.append(f"{path}.{k}: the fake has it, the real answer doesn't")
            else:
                out += differences(real[k], fake[k], f"{path}.{k}")
    elif isinstance(real, list) and isinstance(fake, list):
        if real and fake:
            out += differences(real[0], fake[0], f"{path}[]")
    elif real != fake and "NoneType" not in (real, fake):
        out.append(f"{path}: real {real}, fake {fake}")
    return out


def todoist() -> int:
    secret = token("todoist")
    base = os.environ.get("FRIDAY_API_TODOIST") or API
    raw = Http("Todoist", base, {"Authorization": f"Bearer {secret}"})
    friday = Todoist(secret)
    step = lambda said: print(f"  {said}")  # noqa: E731
    print("Todoist, live:")
    step(f"token works ({friday.check()})")
    projects = raw.json("GET", "/projects", params={"limit": 200})["results"]
    project = next((p for p in projects if p["name"] == PROJECT), None) or raw.json(
        "POST", "/projects", json={"name": PROJECT}
    )
    due = (date.today() + timedelta(days=3)).isoformat()
    made = raw.json("POST", "/tasks", json={"content": "Live check: write a report", "project_id": project["id"],
                                             "due_date": due, "duration": 45, "duration_unit": "minute"})  # fmt: skip
    try:
        seen = next((r for r in friday.read() if r.external_id == str(made["id"])), None)
        assert seen is not None, "the task added there wasn't read"
        kept = raw.json("GET", f"/tasks/{made['id']}").get("duration")  # free plans don't keep a length (11 Nov)
        assert seen.due == due, f"read as due {seen.due}"
        if kept:
            assert seen.minutes == 45, f"Todoist kept 45 min; read as {seen.minutes}"
            step("a task added there reads with its due and length")
        else:
            assert seen.minutes is None, f"Todoist kept no length; read as {seen.minutes}"
            step("a task added there reads with its due (this plan keeps no lengths: none read)")
        friday.write(str(made["id"]), "done")
        assert all(r.external_id != str(made["id"]) for r in friday.read()), "done here, still open there"
        step("done through Friday closes it there")
        friday.write(str(made["id"]), "reopen")
        assert any(r.external_id == str(made["id"]) for r in friday.read()), "opened again here, still closed there"
        step("open again through Friday reopens it there")
        real_task = raw.json("GET", f"/tasks/{made['id']}")
    finally:
        raw.call("DELETE", f"/tasks/{made['id']}")
        step("the check's task deleted")
    from tests.integrations.fake_todoist import FakeTodoist

    fake = FakeTodoist("t")
    fake_task = fake.tasks[fake.add("x", due, 45)]
    drift = differences(shape(real_task), shape(fake_task))
    for d in drift:
        print(f"  drift: task{d}")
    print("  the fake matches Todoist's tasks" if not drift else f"  {len(drift)} difference(s): update the fake")
    return 1 if drift else 0


# The others, read only (11 Nov): the token works, Friday reads your open to-dos through its own connector, and each
# has a title and a due Friday can read. Nothing of yours is changed. Jira and Canvas also need your site:
# FRIDAY_LIVE_SITE (and Jira your email, FRIDAY_LIVE_EMAIL).
READ_ONLY = ("notion", "asana", "linear", "jira", "github", "canvas")


def read_only(kind: str) -> int:
    from friday.integrations.sync import CONNECTORS, local_due

    make = CONNECTORS[kind]
    fields = {"site": os.environ.get("FRIDAY_LIVE_SITE", ""), "email": os.environ.get("FRIDAY_LIVE_EMAIL", "")}
    friday = make(token(kind), {k: v for k, v in fields.items() if k in getattr(make, "fields", ())})
    print(f"{make.name}, live (read only):")
    print(f"  token works ({friday.check()})")
    found = friday.read()
    print(f"  {len(found)} open to-do{'' if len(found) == 1 else 's'} read")
    bad = [r.external_id for r in found if not r.title.strip()]
    assert not bad, f"{len(bad)} read without a title"
    for r in found:
        local_due(r.due, "America/New_York")  # a due Friday can't read fails here, said below
    print("  each has a title, and every due reads")
    return 0


CHECKS = {"todoist": todoist} | {k: (lambda k=k: read_only(k)) for k in READ_ONLY}

if __name__ == "__main__":
    kind = sys.argv[1] if len(sys.argv) > 1 else ""
    if kind not in CHECKS:
        sys.exit(f"Which integration? One of: {', '.join(CHECKS)}")
    try:
        sys.exit(CHECKS[kind]())
    except (ConnectorError, AssertionError, ValueError) as error:
        print(f"  failed: {error}")
        sys.exit(1)
