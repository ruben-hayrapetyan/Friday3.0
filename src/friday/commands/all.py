"""Importing this module registers every command and query."""

from friday.commands import (  # noqa: F401
    ai,
    calendar,
    calendars,
    claude,
    diagnose,
    explain,
    horizon,
    importing,
    inbox,
    insights,
    items,
    kinds,
    learned,
    learning,
    mac,
    mail,
    notify,
    pins,
    planning,
    progress,
    queries,
    rating,
    repeats,
    reviews,
    rules,
    series,
    settings,
    shove,
    tokens,
    undo,
    ways,
)
from friday.commands.registry import REGISTRY

__all__ = ["REGISTRY"]
