"""Split an experiment's user loop over several processes: `--shard i/n` keeps every n-th unit of work starting at i."""
from __future__ import annotations

import sys


def shard() -> tuple[int, int]:
    for a in sys.argv:
        if a.startswith("--shard="):
            i, n = a.split("=")[1].split("/")
            return int(i), int(n)
    return 0, 1


def mine(k: int) -> bool:
    i, n = shard()
    return k % n == i


def suffix() -> str:
    i, n = shard()
    return "" if n == 1 else f"_shard{i}of{n}"
