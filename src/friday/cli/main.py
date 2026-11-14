"""`friday`: one command per verb, generated from `friday.api.verbs` (DESIGN §19). It talks to `fridayd` over HTTP.

Required input fields become arguments, the rest `--options`; `add` takes its quick-add line as the argument. Ids
are accepted with or without their letter (`T42`, `C881`). Values are sent as typed and the server's models coerce
and validate them; mappings and lists of records are given as JSON. Exit codes: 0 success, 1 bad input, 2 server
unreachable, 3 server failure.
"""

import inspect
import json
import os
import re
import tomllib
from pathlib import Path
from types import UnionType
from typing import Annotated, Any, Union, get_args, get_origin

import httpx
import typer
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from friday.api.types import Verb
from friday.api.verbs import VERBS
from friday.cli import render
from friday.cli.render import Clock

CONFIG = Path("~/.config/friday/cli.toml").expanduser()
DEFAULT_SERVER = "http://localhost:8765"
TIMEOUT = httpx.Timeout(330, connect=3)  # `replan` waits for the worker, up to 300 s
ARGUMENT_FIRST = {"add": "text"}  # an optional field taken as the argument
ID_LETTERS = re.compile(r"^[A-Za-z](\d+)$")

app = typer.Typer(
    help="Friday from the terminal. `friday COMMAND --help` for a command's options.", no_args_is_help=True
)


class Failure(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def server() -> str:
    if os.environ.get("FRIDAY_SERVER"):
        return os.environ["FRIDAY_SERVER"].rstrip("/")
    if CONFIG.exists():
        return str(tomllib.loads(CONFIG.read_text()).get("server", DEFAULT_SERVER)).rstrip("/")
    return DEFAULT_SERVER


def call(verb: Verb, payload: dict[str, Any], preview: bool = False) -> Any:
    url, headers = server() + verb.path, {"x-friday-client": "cli"}
    try:
        if verb.method == "GET":
            response = httpx.get(url, params=payload, headers=headers, timeout=TIMEOUT)
        else:
            params = {"preview": "true"} if preview else None
            response = httpx.post(url, json=payload, params=params, headers=headers, timeout=TIMEOUT)
    except httpx.TransportError as error:
        raise Failure(2, f"can't reach Friday at {server()} ({type(error).__name__}); is fridayd running?") from error
    if response.status_code >= 500:
        raise Failure(3, f"Friday failed ({response.status_code}): {response.text[:500]}")
    if response.status_code >= 400:
        raise Failure(1, error_message(response))
    return response.json()


def clock_setting() -> Clock:
    """Your clock (Settings → Appearance → Clock), from the server's settings; the 12-hour clock when it can't say."""
    try:
        response = httpx.get(
            server() + "/api/q/settings", params=None, headers={"x-friday-client": "cli"}, timeout=TIMEOUT
        )
        said = response.json().get("clock") if response.status_code == 200 else None
    except (httpx.HTTPError, ValueError, AttributeError):
        said = None
    return "24h" if said == "24h" else "12h"


def error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text
    if "message" in body:
        return body["message"]
    detail = body.get("detail")
    if isinstance(detail, list):  # the request's own validation
        return "; ".join(f"{'.'.join(str(p) for p in d['loc'][1:]) or 'input'}: {d['msg']}" for d in detail)
    return str(detail)


def value_of(name: str, field: FieldInfo, given: Any) -> Any:
    """What the user typed, as the server's model takes it."""
    if isinstance(given, list):
        return [value_of(name, field, g) for g in given]
    if not isinstance(given, str):
        return given
    if is_id(name) and (match := ID_LETTERS.match(given)):
        return match[1]
    if takes_json(field.annotation):
        try:
            return json.loads(given)
        except ValueError:
            return given
    return given


def is_id(name: str) -> bool:
    return name in ("id", "ids", "after", "before") or name.endswith(("_id", "_ids"))


def takes_json(annotation: Any) -> bool:
    """Mappings, records, lists of records and `Any` are given as JSON."""
    if annotation is Any:
        return True
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return any(takes_json(a) for a in get_args(annotation) if a is not type(None))
    if origin is list:
        return any(takes_json(a) or isinstance(a, type) and issubclass(a, BaseModel) for a in get_args(annotation))
    return origin is dict or isinstance(annotation, type) and issubclass(annotation, BaseModel)


def is_flag(annotation: Any) -> bool:
    return annotation is bool or set(get_args(annotation)) == {bool, type(None)}


def is_list(annotation: Any) -> bool:
    if get_origin(annotation) in (Union, UnionType):
        return any(is_list(a) for a in get_args(annotation))
    return get_origin(annotation) is list and not takes_json(annotation)


def parameter(verb_name: str, name: str, field: FieldInfo) -> inspect.Parameter:
    option, help_text = "--" + name.replace("_", "-"), field.description
    kind = inspect.Parameter.KEYWORD_ONLY
    if ARGUMENT_FIRST.get(verb_name) == name:
        return inspect.Parameter(name, kind, default=None, annotation=Annotated[str | None, typer.Argument()])
    if field.is_required() and is_list(field.annotation):  # `friday late-accept T3 T4`: one argument each
        return inspect.Parameter(name, kind, annotation=Annotated[list[str], typer.Argument(help=help_text)])
    if field.is_required() and not is_flag(field.annotation):
        return inspect.Parameter(name, kind, annotation=Annotated[str, typer.Argument(help=help_text)])
    if is_flag(field.annotation):
        flags = typer.Option(f"{option}/--no-{option[2:]}", help=help_text)
        return inspect.Parameter(name, kind, default=None, annotation=Annotated[bool | None, flags])
    if is_list(field.annotation):
        return inspect.Parameter(name, kind, default=None, annotation=Annotated[list[str] | None, typer.Option(option)])
    return inspect.Parameter(name, kind, default=None, annotation=Annotated[str | None, typer.Option(option)])


def flag(name: str, option: str, help_text: str) -> inspect.Parameter:
    annotation = Annotated[bool, typer.Option(option, help=help_text)]
    return inspect.Parameter(name, inspect.Parameter.KEYWORD_ONLY, default=False, annotation=annotation)


def make_command(name: str, verb: Verb) -> None:
    fields = verb.input.model_fields
    params = [parameter(name, n, f) for n, f in fields.items()]
    params.append(flag("as_json", "--json", "print the raw response"))
    if verb.mutates:
        params.append(flag("preview", "--preview", "show the effect; change nothing"))

    def handler(**given: Any) -> None:
        as_json, preview = given.pop("as_json"), given.pop("preview", False)
        payload = {k: value_of(k, fields[k], v) for k, v in given.items() if v is not None and v != []}
        try:
            response = call(verb, payload, preview)
        except Failure as failure:
            render.error(str(failure))
            raise typer.Exit(failure.code) from failure
        render.use_clock(clock_setting)  # asked only if a time is printed
        render.show(name, response, as_json)

    handler.__signature__ = inspect.Signature(params)  # type: ignore[attr-defined]
    handler.__annotations__ = {p.name: p.annotation for p in params}
    app.command(name.replace("_", "-"), help=verb.summary)(handler)


for verb_name, verb_spec in VERBS.items():
    make_command(verb_name, verb_spec)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
