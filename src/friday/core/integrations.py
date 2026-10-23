"""Settings for the outside world (DESIGN §22): the LLM, Google, Calendar, Gmail, feeds and webhooks. Every one can
also be set in `friday.toml` (§22.9). Secrets never live here."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LlmSettings(Model):
    model: str = "claude-sonnet-5-5"  # reads mail and documents
    small_model: str = "claude-haiku-5-5"  # sorts what comes in: each item's kind, title, deadline or time
    daily_calls: int = Field(50, ge=0)
    daily_tokens: int = Field(500_000, ge=0)


class GoogleSettings(Model):
    client_file: str | None = None  # the Desktop OAuth client JSON from Google Cloud


class GcalSettings(Model):
    read: tuple[str, ...] = ()  # calendar names or ids ("primary")
    trusted: tuple[str, ...] = ()  # their events skip the inbox
    include_all_day: bool = False
    publish: bool = False  # the "Friday" calendar
    publish_debounce_s: int = Field(60, ge=0)


class GmailSettings(Model):
    enabled: bool = False
    query: str = "newer_than:14d -category:promotions -category:social -category:forums"
    max_per_sync: int = Field(50, ge=1)
    sender_domains: tuple[str, ...] = ()
    keywords: tuple[str, ...] = (
        "due", "deadline", "exam", "quiz", "assignment", "submit", "meeting", "invite", "reschedule", "cancelled",
        "prelim", "midterm", "homework", "problem set", "lab report", "rsvp", "form", "application",
    )  # fmt: skip


class IngestSettings(Model):
    poll_min: int = Field(30, ge=1)
    # How calendar events are read when their calendar doesn't name a kind (case is ignored, except in `(?-i:…)`).
    due_pattern: str = r"\b(due|deadline)\b"
    exam_pattern: str = r"\b(exam|midterm|prelim|quiz)\b"
    class_pattern: str = (
        r"(?-i:\b[A-Z]{2,5} ?\d{3,4}[A-Z]?\b)|\b(lecture|lab|laboratory|discussion|recitation|seminar|tutorial)\b"
    )


class FeedSettings(Model):
    """An ICS feed, matched to its `sources` row by name."""

    name: str
    url: str
    trusted: bool = False
    due_pattern: str | None = None  # instead of ingest's
    class_pattern: str | None = None


class Webhook(Model):
    url: str
    events: tuple[Literal["block.started", "slack.low", "plan.changed", "item.done"], ...] = (
        "block.started", "slack.low", "plan.changed", "item.done",
    )  # fmt: skip


INTEGRATION_TYPES = {
    "llm": LlmSettings,
    "google": GoogleSettings,
    "gcal": GcalSettings,
    "gmail": GmailSettings,
    "ingest": IngestSettings,
    "sources": tuple[FeedSettings, ...],
    "webhooks": tuple[Webhook, ...],
}
INTEGRATION_DEFAULTS = {
    "llm": LlmSettings(),
    "google": GoogleSettings(),
    "gcal": GcalSettings(),
    "gmail": GmailSettings(),
    "ingest": IngestSettings(),
    "sources": (),
    "webhooks": (),
}
