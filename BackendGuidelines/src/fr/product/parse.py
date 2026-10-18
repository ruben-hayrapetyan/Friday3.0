"""Text -> typed constraints with Claude (RQ16). The model only translates; `constraints.apply` compiles.

Claude runs through the `claude` CLI in print mode with no tools, no MCP servers and no saved session, exactly as the
Friday app already runs it (UI/Sources/Calendar/ClaudePanel.swift), so no API key is needed. `Prompt` holds the
variants E019 compares; `DEFAULT` is the one chosen there.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .constraints import Parse

MODEL = "claude-sonnet-5-5"
CANDIDATES = [Path.home() / ".local/bin/claude", Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")]

ROLE = """You translate what a student writes about their life and habits into typed scheduling constraints for Friday,
a planner. You never make or suggest a schedule; a separate deterministic engine does that. You only translate.
Reply with one JSON object matching the schema: {"constraints": [...], "unsupported": [...], "questions": [...]}."""

GUIDE = """How to translate:
- Hard vs soft. Words like never, can't, don't, no, must, only, off limits, sacred mean strength "hard". Words like
  prefer, rather, try, ideally, if possible, like, best, mostly mean a soft strength: "mild" for slight wishes, "medium"
  by default, "strong" for strongly / really / much prefer.
- Times are 24 h "HH:MM". A window that runs into the night ("after 11pm") ends in the morning ("07:00"), not at
  midnight. A window with no start or end leaves it null. days null = every day.
- Sleep: "nights" are named by the evening they start on. "Up at 7 on weekdays" is the nights sun, mon, tue, wed, thu.
  A bedtime after midnight is written as is ("01:30").
- Targets: use course names and task titles exactly as in the context. kinds are task kinds (assignment covers problem
  sets, labs, essays; reading; project; exam_prep; chore; errand; goal; habit; routine). energy deep = focused work.
  A target with every field empty means all work.
- Fixed things at set times (gym, a job, practice, an appointment, a call) are commitments. Use dates for one-off days.
- Buffers are minutes kept clear around a kind of event (class, meeting, other).
- Order constraints name two tasks by a title substring that matches exactly one task each.
- Ask a question (in "questions") instead of guessing when a time, day or amount the constraint needs is missing; add
  the constraints that are clear anyway.
- If the text asks for something these types cannot express, put it in "unsupported" with a short reason. Never
  approximate it with a constraint that means something else.
- Text that only permits something ("I don't mind working late"), thanks, or questions about the schedule produce no
  constraint.
- Each constraint gets "source" (the words it comes from) and "paraphrase" (one short sentence the user will confirm)."""

# E019 round 2: additions after round 1's errors on the tuning split
GUIDE2 = GUIDE + """
- Saying something is useless, impossible or unbearable ("blocks under 45 minutes are useless to me", "I can't focus
  longer than 90 minutes") is a hard constraint.
- A request that is not a constraint at all (a question about the schedule, an action such as sending an email or
  setting an alarm, a goal about grades) goes to "unsupported" with a short reason, so the user hears that Friday did
  not act on it."""
# After E019, from use: the schema gained task types, exclusions and a soft one sitting (decision 36)
GUIDE3 = GUIDE2 + """
- Each task in the context has a "type" (problem_set, essay, lab, reading, exam_prep, project, email, other), finer
  than its kind. Use target.types for "problem sets", "essays", "labs"; use exclude_types / exclude_titles for "other
  than", "except", "as opposed to".
- Wanting tasks done in one go, in one sitting, without breaking them up is one_sitting: hard if they must never be
  split, soft ("if possible", "I like to", "I'd rather") otherwise. A preference for which tasks to split first is two
  one_sitting constraints: a weaker strength for the ones that may be split, a stronger one for the rest."""
GUIDES = {0: None, 1: GUIDE, 2: GUIDE2, 3: GUIDE3}


@dataclass
class Prompt:
    name: str
    guide: int = 1  # 0 = none, 1 = GUIDE, 2 = GUIDE2
    examples: list[dict] = field(default_factory=list)  # [{"text":..., "reply": {...}}]
    enforce_schema: bool = True  # pass the JSON schema to the CLI (structured output)
    retries: int = 1  # re-ask once with the validation error

    def system(self) -> str:
        parts = [ROLE]
        if self.guide:
            parts.append(GUIDES[int(self.guide)])
        if not self.enforce_schema:
            parts.append("JSON schema of the reply:\n" + json.dumps(schema()))
        if self.examples:
            ex = "\n\n".join(f"Text: {e['text']}\nReply: {json.dumps(e['reply'])}" for e in self.examples)
            parts.append("Examples (with a different context):\n" + ex)
        return "\n\n".join(parts)


def executable() -> Path:
    for p in CANDIDATES:
        if p.exists() and os.access(p, os.X_OK):
            return p
    raise FileNotFoundError("the claude CLI is not installed (looked in ~/.local/bin, /opt/homebrew/bin, /usr/local/bin)")


_WORKDIR = Path(tempfile.gettempdir()) / "friday-parse"


def call_claude(system: str, user: str, schema: dict | None, model: str = MODEL, timeout: float = 180) -> dict:
    """One print-mode call. Returns {"text", "structured", "cost", "seconds"}."""
    args = [str(executable()), "-p", user, "--model", model, "--output-format", "json", "--system-prompt", system,
            "--tools", "", "--strict-mcp-config", "--no-session-persistence"]
    if schema is not None:
        args += ["--json-schema", json.dumps(schema)]
    _WORKDIR.mkdir(exist_ok=True)
    t = time.perf_counter()
    out = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=timeout,
                         cwd=_WORKDIR)
    if out.returncode != 0:
        raise RuntimeError(f"claude exited {out.returncode}: {out.stderr.strip()[:300] or out.stdout.strip()[:300]}")
    env = json.loads(out.stdout)
    return dict(text=env.get("result", ""), structured=env.get("structured_output"),
                cost=env.get("total_cost_usd", 0.0), seconds=time.perf_counter() - t)


def schema() -> dict:
    """Parse's JSON schema without the keywords the CLI's strict validator rejects (pydantic's `discriminator`)."""
    def clean(x):
        if isinstance(x, dict):
            return {k: clean(v) for k, v in x.items() if k != "discriminator"}
        if isinstance(x, list):
            return [clean(v) for v in x]
        return x
    return clean(Parse.model_json_schema())


def _json_in(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in the reply")
    return json.loads(m.group(0))


def user_message(text: str, context: dict) -> str:
    return f"Context:\n{json.dumps(context)}\n\nThe student wrote:\n{text}"


@dataclass
class Result:
    parse: Parse | None
    raw: object
    error: str | None
    cost: float
    seconds: float
    calls: int


def parse_text(text: str, context: dict, prompt: Prompt, model: str = MODEL, caller=call_claude) -> Result:
    system = prompt.system()
    user = user_message(text, context)
    sch = schema() if prompt.enforce_schema else None
    cost = secs = 0.0
    raw: object = None
    err = None
    for attempt in range(1 + prompt.retries):
        r = caller(system, user, sch, model)
        cost += r["cost"]
        secs += r["seconds"]
        try:
            raw = r["structured"] if r.get("structured") is not None else _json_in(r["text"])
            return Result(Parse.model_validate(raw), raw, None, cost, secs, attempt + 1)
        except (ValueError, ValidationError) as e:
            err = str(e)[:1500]
            raw = raw if raw is not None else r["text"]
            user = (user_message(text, context) + f"\n\nYour previous reply was not valid:\n{err}\n"
                    "Reply again with a corrected JSON object.")
    return Result(None, raw, err, cost, secs, 1 + prompt.retries)


DEFAULT = Prompt("guide3", guide=3)  # guide2 scored 99.0% on E019's held-out split; guide3 only adds lines for new types
