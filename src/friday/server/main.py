"""`fridayd`: `serve` (the default) runs the API, worker and jobs; `init` sets the timezone and sleep times;
`google-login` connects a Google account (as Connect in Settings → Integrations does; again for another account);
`google-calendars` lists every account's calendars for `gcal.read`; `demo` serves a sample term to try Friday on."""

import argparse
import logging
import os
from pathlib import Path

import uvicorn

from friday.commands.registry import run
from friday.core.db import connect
from friday.core.paths import config_path
from friday.engine.sampler import default_chains
from friday.planner.store import load_settings
from friday.server import logs
from friday.server.app import create_app, query_by_get, wall_clock
from friday.server.config import apply_config
from friday.server.demo import run_demo
from friday.server.mcp import serve_stdio
from friday.sim.students import STUDENTS
from friday.sync import gcal, google_auth

DATA_DIR = Path(os.environ.get("FRIDAY_DATA_DIR", "~/.local/share/friday")).expanduser()
WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="fridayd", description="The Friday daemon")
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    commands = parser.add_subparsers(dest="command")
    serve = commands.add_parser("serve", help="run the API, the solver worker and the jobs")
    serve.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to reach it from your phone over Tailscale")
    serve.add_argument("--port", type=int, help="default: settings server.port (8765)")
    init = commands.add_parser("init", help="set the timezone and sleep times (run once)")
    init.add_argument("--timezone", default=local_timezone(), help="IANA name; detected: %(default)s")
    init.add_argument("--bedtime", default="23:30")
    init.add_argument("--wake", default="07:30")
    init.add_argument("--margin-min", type=int, default=60, help="time past bedtime used only when a deadline needs it")
    commands.add_parser("mcp", help="an MCP server on stdio for a local assistant (FRIDAY_TOKEN; daemon running)")
    login = commands.add_parser(
        "google-login",
        help="connect a Google account's calendars, and its mail if gmail.enabled (opens the browser); "
        "run it again to add another account",
    )
    login.add_argument(
        "--client-file", type=Path, help="default: google.client_file, else google_client.json beside friday.toml"
    )
    commands.add_parser("google-calendars", help="list each Google account's calendars' names and ids, for gcal.read")
    demo = commands.add_parser("demo", help="a sample student's term with stand-in Google, Gmail and AI")
    demo.add_argument("--port", type=int, default=8799)
    demo.add_argument("--case", choices=list(STUDENTS), help="a Cornell student, from very light to overloaded")
    demo.add_argument("--ready", action="store_true", help="three weeks into using Friday (sim/history.py)")
    args = parser.parse_args(argv)
    if args.command == "demo":  # never in your own data folder
        name = "-".join(["friday-demo", *([args.case] if args.case else []), *(["lived"] if args.ready else [])])
        folder = args.data_dir if args.data_dir != DATA_DIR else DATA_DIR.with_name(name)
        return run_demo(folder, args.port, serve_forever, initialize, args.case, args.ready)
    args.data_dir.mkdir(parents=True, exist_ok=True)
    db_path = args.data_dir / "friday.db"
    if args.command == "init":
        initialize(db_path, args.timezone, args.bedtime, args.wake, args.margin_min)
    elif args.command == "mcp":
        conn = connect(db_path)
        port = load_settings(conn)["server"].port
        conn.close()
        serve_stdio(port, query_by_get)
    elif args.command == "google-calendars":
        google_calendars(db_path.parent)
    elif args.command == "google-login":
        google_login(db_path, args.client_file)
    else:
        serve_forever(db_path, getattr(args, "host", "127.0.0.1"), getattr(args, "port", None))


def serve_forever(db_path: Path, host: str, port: int | None) -> None:
    conn = connect(db_path)
    server = load_settings(conn)["server"]
    conn.close()
    where = logs.install(db_path.parent, server.log_level)
    logging.getLogger("friday").info(
        "fridayd starting on %s:%s, data in %s, log %s", host, port or server.port, db_path.parent, where
    )
    app = create_app(db_path, web_dist=WEB_DIST)
    # Open SSE streams never end on their own; without a limit they would hold shutdown forever.
    uvicorn.run(app, host=host, port=port or server.port, log_level=server.log_level, timeout_graceful_shutdown=2)


def initialize(db_path: Path, timezone: str | None, bedtime: str, wake: str, margin_min: int) -> None:
    if timezone is None:
        raise SystemExit("couldn't detect your timezone; pass --timezone, e.g. America/New_York")
    conn = connect(db_path)
    now = wall_clock()

    def setting(key: str, value: object) -> None:
        run(conn, "settings_set", {"key": key, "value": value}, now_utc=now, actor="cli", provisional=False)

    settings = load_settings(conn)
    setting("time", settings["time"].model_dump() | {"timezone": timezone})
    setting("sleep", dict.fromkeys(WEEKDAYS, {"bedtime": bedtime, "wake": wake, "margin_min": margin_min}))
    # Plans depend on the chain count, so it is written down rather than detected at every start.
    setting("engine", settings["engine"].model_dump() | {"chains": settings["engine"].chains or default_chains()})
    conn.close()
    print(f"Friday is set up in {db_path} ({timezone}, sleep {bedtime}–{wake}). Start it with `fridayd`.")


def google_login(db_path: Path, client_file: Path | None) -> None:
    conn = connect(db_path)
    apply_config(conn, wall_clock(), config_path())  # so client_file is read from friday.toml even before serving
    settings = load_settings(conn)
    conn.close()
    path = client_file.expanduser() if client_file else google_auth.client_file(settings["google"].client_file)
    if not path.exists():
        raise SystemExit(f"no OAuth client JSON at {path}: choose it in Settings → Integrations, or pass --client-file")
    account = google_auth.login(path, db_path.parent, google_auth.scopes(settings["gmail"].enabled))
    kept = google_auth.client_file(settings["google"].client_file)
    if not kept.exists():  # a key file named here is kept where Friday looks, so Connect in the app works from now on
        google_auth.keep_client(kept, path.read_text())
    print(
        f"Google is connected for {account}; its token is in {google_auth.secrets_file(db_path.parent)}. "
        "Run this again to add another account."
    )


def google_calendars(folder: Path) -> None:
    apis = google_auth.per_account(None, folder, google_auth.calendar)
    if not apis:
        raise SystemExit("Google isn't connected yet: run `fridayd google-login` first")
    print("Switch them on in Settings → Integrations, or name them in gcal.read in friday.toml.")
    for account, api in apis.items():
        print(f"\n{account or 'Your Google account'}:")
        for entry in gcal.paged(api().calendarList()):
            name = "primary" if entry.get("primary") else entry.get("summary", "")
            also = f"  (also: {entry.get('summary')})" if entry.get("primary") else ""
            print(f"  {name!r}{also}\n      id {entry['id']}, {entry.get('accessRole', '')}")


def local_timezone() -> str | None:
    if os.environ.get("TZ"):
        return os.environ["TZ"]
    target = os.path.realpath("/etc/localtime")
    return target.split("zoneinfo/", 1)[1] if "zoneinfo/" in target else None


if __name__ == "__main__":
    main()
