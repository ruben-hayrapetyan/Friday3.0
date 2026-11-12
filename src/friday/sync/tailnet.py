"""This Mac on your tailnet (C61): its Tailscale address (100.64.0.0/10, as Tailscale gives them) and its name there
(`laptop.example.ts.net`), read from the system each time they're asked for, so Friday follows Tailscale being turned
on, off or signed into another tailnet. None when Tailscale isn't running here."""

import ipaddress
import json
import re
import shutil
import subprocess
from pathlib import Path

TAILNET = ipaddress.ip_network("100.64.0.0/10")
APP_CLI = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")


def run(*command: str) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def address(listing: str | None = None) -> str | None:
    """The first IPv4 address of this machine inside Tailscale's range; `listing` is `ifconfig`'s output."""
    text = listing if listing is not None else run("ifconfig") or run("ip", "-4", "addr")
    for found in re.findall(r"inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", text):
        if ipaddress.ip_address(found) in TAILNET:
            return found
    return None


def cli() -> str | None:
    return shutil.which("tailscale") or (str(APP_CLI) if APP_CLI.exists() else None)


def name(status: str | None = None) -> str | None:
    """This machine's name on the tailnet (MagicDNS), from `tailscale status --json`; `status` is that output."""
    if status is None:
        tool = cli()
        status = run(tool, "status", "--json") if tool else ""
    try:
        found = json.loads(status or "{}").get("Self", {}).get("DNSName", "")
    except json.JSONDecodeError:
        return None
    return found.rstrip(".") or None
