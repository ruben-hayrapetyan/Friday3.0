"""Settings for the outside world (DESIGN §22): the LLM, Google, Calendar, Gmail, feeds and webhooks. Every one can
also be set in `friday.toml` (§22.9). Secrets never live here."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


# The AI Friday reads with (28 Oct: "check whether friday only works with claude or whether it is compatible with
# OpenAI, or any other agent"; "what about for muse, instinct, gemini, grok, and some open source ones too").
Provider = Literal["claude", "openai", "gemini", "grok", "muse", "compatible", "local"]


@dataclass(frozen=True)
class ProviderInfo:
    name: str  # what the app calls it
    address: str | None  # its OpenAI-style chat API (None: Claude's own, or the one you give)
    section: str  # its key's section of secrets.toml
    variable: str | None  # and the variable that can hold it instead
    models: tuple[str, str] | None  # (model, small_model) when you haven't named them; None: chosen from its list
    needs_key: bool = True
    note: str = ""


PROVIDERS: dict[str, ProviderInfo] = {
    "claude": ProviderInfo("Claude", None, "anthropic", "ANTHROPIC_API_KEY", ("claude-sonnet-5-5", "claude-haiku-5-5")),
    "openai": ProviderInfo("GPT", "https://api.openai.com/v1", "openai", "OPENAI_API_KEY", ("gpt-5", "gpt-5-mini")),
    # Model names change too often to guess: chosen from the service's own list once its key is in.
    "gemini": ProviderInfo(
        "Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini", "GEMINI_API_KEY", None
    ),  # fmt: skip
    "grok": ProviderInfo("Grok", "https://api.x.ai/v1", "xai", "XAI_API_KEY", None),
    "muse": ProviderInfo(
        "Muse",
        "https://api.meta.ai/v1",
        "meta",
        "META_API_KEY",
        None,
        note="Meta's API is in preview: if the check fails, its address may have changed",
    ),  # fmt: skip
    "compatible": ProviderInfo("AI", None, "compatible", "FRIDAY_AI_KEY", None, needs_key=False),
    # Open models run on this Mac by Ollama (ingest/local_models.py): no key, no account, slow.
    "local": ProviderInfo("AI", None, "local", None, None, needs_key=False),
}
DEFAULT_MODELS = {p: info.models for p, info in PROVIDERS.items() if info.models}
KNOWN_DEFAULTS = {m for pair in DEFAULT_MODELS.values() for m in pair}


class LlmSettings(Model):
    provider: Provider = "claude"
    model: str = DEFAULT_MODELS["claude"][0]  # reads mail and documents; "" until one is chosen
    small_model: str = DEFAULT_MODELS["claude"][1]  # sorts what comes in: each item's kind, title, deadline or time
    base_url: str | None = None  # another service's OpenAI-style address, or a named one's when it moved
    # Claude, OpenAI and Gemini, asked through their command on this Mac or through an API key: your choice (C95,
    # 10 Nov: "the user should have the choice between cli commands or api key"). "key" asks through the key alone.
    via: Literal["command", "key"] = "command"
    daily_calls: int = Field(50, ge=0)
    daily_tokens: int = Field(500_000, ge=0)

    @field_validator("base_url")
    @classmethod
    def an_address(cls, url: str | None) -> str | None:
        url = (url or "").strip() or None
        if url is not None and not url.startswith(("http://", "https://")):
            raise ValueError('an address starting http:// or https:// ("http://localhost:11434/v1")')
        return url

    @model_validator(mode="after")
    def models_of_the_provider(self) -> "LlmSettings":
        """Another provider's model names, kept after a switch, become this one's own (or none, to choose from its
        list): a provider set alone (friday.toml) still reads with models it has. Names you gave are left as given; one
        model serves for both unless you name a second."""
        mine = DEFAULT_MODELS.get(self.provider)
        if self.model in KNOWN_DEFAULTS and (mine is None or self.model not in mine):
            self.model = mine[0] if mine else ""
        if self.small_model in KNOWN_DEFAULTS and (mine is None or self.small_model not in mine):
            self.small_model = mine[1] if mine else ""
        if mine and not self.model:
            self.model = mine[0]
        if mine and not self.small_model:
            self.small_model = mine[1]
        if not self.small_model:
            self.small_model = self.model
        return self

    @property
    def address(self) -> str | None:
        """Where its chat API is: the one you gave, else the provider's own."""
        return self.base_url or PROVIDERS[self.provider].address


class ClaudeSettings(Model):
    """Ask Claude (commands/claude.py). Claude only proposes; this says which proposals wait for your yes."""

    events_without_asking: bool = False  # changes to calendar events apply at once, with Undo; the rest still ask


class GoogleSettings(Model):
    client_file: str | None = None  # the Desktop OAuth client JSON from Google Cloud


class GcalSettings(Model):
    read: tuple[str, ...] = ()  # calendar names or ids ("primary")
    trusted: tuple[str, ...] = ()  # their events skip the inbox
    include_all_day: bool = False
    publish: bool = False  # the "Friday" calendar
    publish_debounce_s: int = Field(60, ge=0)
    new_events_to: str | None = None  # a calendar's id: events you make in Friday are saved there too (COMBINED.md 69)


# An email about an event is one for the Inbox (29 Oct: "this is an email about an event so it should be put into
# inbox", a film screening sent to a Cornell list): the words such a subject says it with, beside the deadlines'.
# 30 Oct: "Invitation to Global Careers Week" was skipped as bulk mail: a keyword matches itself and its plural, and
# "invite" isn't in "invitation" or "invited".
EVENT_WORDS = (
    "join us", "screening", "talk", "seminar", "info session", "information session", "workshop", "panel",
    "lecture", "event", "conversation with", "reception", "symposium", "webinar", "career fair", "showcase",
    "invitation", "invited", "careers week", "social",
)  # fmt: skip


class GmailSettings(Model):
    enabled: bool = False
    # Not promotions or social media; the Forums tab is read, where a university's lists put its talks and events.
    query: str = "newer_than:14d -category:promotions -category:social"
    max_per_sync: int = Field(50, ge=1)
    sender_domains: tuple[str, ...] = ()
    keywords: tuple[str, ...] = (
        "due", "deadline", "exam", "quiz", "assignment", "submit", "meeting", "invite", "reschedule", "cancelled",
        "prelim", "midterm", "homework", "problem set", "lab report", "rsvp", "form", "application", *EVENT_WORDS,
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
    "claude": ClaudeSettings,
    "google": GoogleSettings,
    "gcal": GcalSettings,
    "gmail": GmailSettings,
    "ingest": IngestSettings,
    "sources": tuple[FeedSettings, ...],
    "webhooks": tuple[Webhook, ...],
}
INTEGRATION_DEFAULTS = {
    "llm": LlmSettings(),
    "claude": ClaudeSettings(),
    "google": GoogleSettings(),
    "gcal": GcalSettings(),
    "gmail": GmailSettings(),
    "ingest": IngestSettings(),
    "sources": (),
    "webhooks": (),
}
