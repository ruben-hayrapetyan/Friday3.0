"""Mail written in HTML read as the text it shows: a line break or a rule starts a new line."""

from friday.core.html_text import html_text


def test_a_self_closed_break_or_rule_starts_a_new_line() -> None:
    assert html_text("Lab report<br/>due Friday<hr/>Prof") == "Lab report\ndue Friday\nProf"
    assert html_text("one<img src='x'/>two") == "onetwo"  # anything else self-closed adds nothing
