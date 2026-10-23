"""Importing this module registers every command and query."""

from friday.commands import (  # noqa: F401
    ai,
    calendar,
    calendars,
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
    mail,
    notify,
    pins,
    planning,
    progress,
    queries,
    repeats,
    reviews,
    rules,
    series,
    settings,
    shove,
    tokens,
    undo,
)
from friday.commands.registry import REGISTRY

__all__ = ["REGISTRY"]
