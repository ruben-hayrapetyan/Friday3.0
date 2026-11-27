"""Random tests for the rules fixed from "Friday Notes-3" (27 Nov): the user asked for "hundreds + random tests", so
each rule is checked over many generated cases, not only the ones the notes showed.

- A calendar repeat with no rule of its own is read from the times seen (commands/series.py weekdays_rule): the
  notes' birthdays read "every Tuesday".
- An event is on a planning day by its own dates when it's all day, else by its hours (core/time.py event_on_day,
  event_day): the notes' Black Friday was under Thursday."""

from datetime import date, datetime, timedelta

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from friday.commands.series import DAYS, weekdays_rule
from friday.core.time import event_day, event_on_day, to_utc

MANY = settings(max_examples=600, deadline=None)
ZONES = ["America/New_York", "America/Chicago", "America/Los_Angeles", "Europe/London", "Asia/Tokyo", "Asia/Kolkata",
         "Australia/Sydney", "Pacific/Auckland", "UTC"]  # fmt: skip
first_days = st.dates(min_value=date(2025, 1, 1), max_value=date(2027, 12, 1))
clock = st.times().map(lambda t: t.replace(second=0, microsecond=0))


def at(day: date, hh_mm: str = "10:00") -> str:
    return f"{day.isoformat()}T{hh_mm}"


# --- a repeat read from the times seen ------------------------------------------------------------------------------


@MANY
@given(first_days, st.sets(st.integers(0, 6), min_size=1, max_size=6), st.integers(2, 6), clock)
def test_a_weekly_repeat_on_any_days_is_read_weekly_on_those_days(start: date, days: set[int], weeks: int, t) -> None:
    monday = start - timedelta(days=start.weekday())
    seen = [at(monday + timedelta(weeks=w, days=d), t.strftime("%H:%M")) for w in range(weeks) for d in sorted(days)]
    assert weekdays_rule(seen) == "FREQ=WEEKLY;BYDAY=" + ",".join(DAYS[d] for d in sorted(days))


@MANY
@given(first_days, st.integers(1, 6), clock)
def test_every_day_of_the_week_seen_is_daily(start: date, weeks: int, t) -> None:
    seen = [at(start + timedelta(days=n), t.strftime("%H:%M")) for n in range(7 * weeks)]
    assert weekdays_rule(seen) == "FREQ=DAILY"


@MANY
@given(first_days, st.integers(2, 4), st.integers(2, 5))
def test_every_few_weeks_on_one_day_is_read_with_its_interval(start: date, every: int, times: int) -> None:
    seen = [at(start + timedelta(weeks=every * n)) for n in range(times)]
    # every 4 weeks from 1 Feb lands on 1 Mar: as much monthly as four-weekly, said monthly
    assume(len({s[8:10] for s in seen}) > 1)
    assert weekdays_rule(seen) == f"FREQ=WEEKLY;INTERVAL={every};BYDAY={DAYS[start.weekday()]}"


@MANY
@given(st.integers(2025, 2027), st.integers(1, 9), st.integers(1, 28), st.integers(2, 3))
def test_the_same_day_of_the_month_is_monthly(year: int, month: int, day: int, times: int) -> None:
    seen = [at(date(year, month + n, day)) for n in range(times)]
    assert weekdays_rule(seen) == "FREQ=MONTHLY"


@MANY
@given(st.integers(2020, 2026), st.integers(1, 12), st.integers(1, 28), st.integers(2, 3), st.booleans())
def test_the_same_date_each_year_is_yearly(year: int, month: int, day: int, times: int, whole: bool) -> None:
    seen = [at(date(year + n, month, day), "00:00" if whole else "19:00") for n in range(times)]
    assert weekdays_rule(seen) == "FREQ=YEARLY"


@MANY
@given(first_days)
def test_a_whole_day_seen_once_is_yearly(day: date) -> None:
    """The notes' birthdays: seen once in the weeks the Mac app sends; never "every <weekday>"."""
    assert weekdays_rule([at(day, "00:00")]) == "FREQ=YEARLY"


@MANY
@given(first_days, clock.filter(lambda t: (t.hour, t.minute) != (0, 0)))
def test_a_timed_one_seen_once_is_weekly_on_its_day(day: date, t) -> None:
    assert weekdays_rule([at(day, t.strftime("%H:%M"))]) == f"FREQ=WEEKLY;BYDAY={DAYS[day.weekday()]}"


@MANY
@given(st.lists(st.tuples(first_days, clock), min_size=1, max_size=12))
def test_any_times_seen_give_a_rule_friday_can_say(seen: list) -> None:
    """Whatever comes in, a rule of one of the frequencies Friday describes, never an error or an empty one."""
    rule = weekdays_rule([at(d, t.strftime("%H:%M")) for d, t in seen])
    assert rule.split(";")[0] in {"FREQ=DAILY", "FREQ=WEEKLY", "FREQ=MONTHLY", "FREQ=YEARLY"}
    if rule.startswith("FREQ=WEEKLY") and "BYDAY=" in rule:
        days = rule.split("BYDAY=")[1].split(",")
        assert days and set(days) <= set(DAYS) and len(days) < 7


# --- which planning day an event is on ------------------------------------------------------------------------------


@MANY
@given(st.sampled_from(ZONES), first_days, st.integers(1, 5), st.integers(-3, 8), st.integers(0, 360))
def test_an_all_day_event_is_on_its_own_dates_whatever_hour_the_day_starts(
    tz: str, first: date, length: int, offset: int, day_start: int
) -> None:
    start = to_utc(datetime.combine(first, datetime.min.time()), tz)
    end = to_utc(datetime.combine(first + timedelta(days=length), datetime.min.time()), tz)
    day = first + timedelta(days=offset)
    assert event_on_day(start, end, day, tz, day_start) == (0 <= offset < length)
    assert event_day(start, end, tz, day_start) == first


@MANY
@given(st.sampled_from(ZONES), first_days, st.integers(1, 5), st.integers(60, 360))
def test_tomorrows_all_day_event_is_never_todays(tz: str, today: date, length: int, day_start: int) -> None:
    """The notes' case: Black Friday (tomorrow, from midnight) under Thursday, whose day runs to 4am."""
    tomorrow = today + timedelta(days=1)
    start = to_utc(datetime.combine(tomorrow, datetime.min.time()), tz)
    end = to_utc(datetime.combine(tomorrow + timedelta(days=length), datetime.min.time()), tz)
    assert not event_on_day(start, end, today, tz, day_start)
    assert event_on_day(start, end, tomorrow, tz, day_start)


@MANY
@given(
    st.sampled_from(ZONES),
    first_days,
    st.integers(0, 23),
    st.integers(0, 59),
    st.integers(15, 240),
    st.integers(0, 360),
)
def test_a_timed_event_is_on_the_day_whose_hours_it_starts_in(
    tz: str, day: date, hour: int, minute: int, minutes: int, day_start: int
) -> None:
    """1am belongs to the day before when days start at 4am; a timed event never takes a date's whole day."""
    local = datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
    start = to_utc(local, tz)
    end = start + minutes
    if hour * 60 + minute == 0 and minutes % 1440 == 0:
        return  # midnight to midnight is all day
    owner = day - timedelta(days=1) if hour * 60 + minute < day_start else day
    assert event_day(start, end, tz, day_start) == owner
    assert event_on_day(start, end, owner, tz, day_start)
