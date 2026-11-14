"""Presets: named facet defaults (DESIGN §6.2). They are settings data; these are the built-in ones."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, model_validator

from friday.core.items import Amount, Certainty, Energy, Firmness, Shape, When


class Preset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    when: When | None = None
    amount: Amount | None = None
    duration_units: int | None = None
    min_units: int | None = None
    ideal_units: int | None = None
    max_units: int | None = None
    target_units: int | None = None
    daily_ceiling_units: int | None = None
    shape: Shape | None = None
    min_chunk_units: int | None = None
    chunk_cost: float | None = None
    firmness: Firmness | None = None
    importance: int | None = None
    neglect_carry: float | None = None
    energy: Energy | None = None
    certainty: Certainty | None = None
    event_kind: str | None = None
    pacing: Literal["linear", "front", "back", "none"] = "none"

    @model_validator(mode="before")
    @classmethod
    def no_spread(cls, value: Any) -> Any:
        """A kind saved before 14 Nov may say its work is spread or clustered: tasks no longer are (a rule says it,
        for the work you name), so that is dropped rather than refused."""
        if isinstance(value, dict) and "spread" in value:
            return {k: v for k, v in value.items() if k != "spread"}
        return value


# School kinds (C97): a student's; out of school (Setup asks) they are hidden and never guessed.
SCHOOL_KINDS = frozenset({"Assignment", "Reading", "Exam prep", "Class", "Exam"})

DEFAULT_PRESETS = {
    # A to-do whose title says nothing more (C97): "Book dentist", "Call the landlord". Short, in one go; your timer
    # teaches Friday the real length, and the app it came from gives its own when it has one.
    "Task": Preset(when="window", amount="fixed", duration_units=2, shape="one_sitting", firmness="hard"),
    # From a work tracker (Asana, Jira, Linear, GitHub, Trello, Notion): an hour, in sittings, its due a deadline.
    "Work task": Preset(when="window", amount="fixed", duration_units=4, shape="split", min_chunk_units=2,
                        chunk_cost=0.1, firmness="hard", energy="deep"),
    "Assignment": Preset(when="window", amount="fixed", duration_units=8, shape="split", min_chunk_units=2,
                         chunk_cost=0.1, firmness="hard", energy="deep", importance=3),
    "Project": Preset(when="window", amount="fixed", duration_units=40, shape="split", min_chunk_units=4,
                      chunk_cost=0.1, firmness="hard", energy="deep", pacing="linear"),
    "Reading": Preset(when="window", amount="fixed", duration_units=4, shape="split", min_chunk_units=2,
                      chunk_cost=0.1, firmness="soft", energy="light"),
    # Hour-long sessions, a sitting costing half another kind's: spread over days only when a rule says so (14 Nov).
    "Exam prep": Preset(when="window", amount="fixed", duration_units=12, shape="split", min_chunk_units=4,
                        chunk_cost=0.05, firmness="hard", energy="deep"),
    "Class": Preset(when="fixed", event_kind="class"),
    "Exam": Preset(when="fixed", event_kind="exam"),
    "Meeting": Preset(when="fixed", event_kind="meeting"),
    "Appointment": Preset(when="fixed", event_kind="other"),
    "Event": Preset(when="fixed", event_kind="other"),
    "Errand": Preset(when="window", amount="fixed", duration_units=4, shape="one_sitting", firmness="none",
                     energy="physical"),
    "Chore": Preset(when="window", amount="fixed", duration_units=2, shape="one_sitting", firmness="none",
                    energy="physical"),
    "Routine": Preset(when="window", amount="elastic", min_units=2, ideal_units=3, max_units=3,
                      shape="one_sitting", firmness="none"),
    "Habit": Preset(when="window", amount="fixed", duration_units=2, shape="one_sitting", firmness="none"),
    "Goal": Preset(when="window", amount="target", target_units=12, shape="split", min_chunk_units=2,
                   chunk_cost=0.1, firmness="none", energy="deep", neglect_carry=0.5),
    "Side project": Preset(when="anytime", amount="open", daily_ceiling_units=4, shape="split",
                           min_chunk_units=3, chunk_cost=0.1, firmness="none", energy="deep"),
    "Maybe": Preset(when="window", amount="fixed", duration_units=4, shape="one_sitting", firmness="none",
                    certainty="tentative"),
}  # fmt: skip


def in_use(presets: dict[str, Preset], school: bool) -> dict[str, Preset]:
    """The kinds Friday may guess and offer you: all yours, or, out of school, all but the school ones (C97)."""
    return presets if school else {k: v for k, v in presets.items() if k not in SCHOOL_KINDS}
