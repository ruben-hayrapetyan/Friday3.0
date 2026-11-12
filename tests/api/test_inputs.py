"""What the API's input models refuse before a command runs (src/friday/api/commands.py)."""

import pytest
from pydantic import ValidationError

from friday.api.commands import DoneInput


def test_the_time_a_task_took_is_at_least_a_minute() -> None:
    # `done --actual-min -30` was kept as a completion of -30 minutes, which estimates and your speed then learned from
    # (audit, 12 Nov)
    for wrong in (-30, 0):
        with pytest.raises(ValidationError):
            DoneInput(id=1, actual_min=wrong)
    assert DoneInput(id=1, actual_min=1).actual_min == 1
    assert DoneInput(id=1).actual_min is None
