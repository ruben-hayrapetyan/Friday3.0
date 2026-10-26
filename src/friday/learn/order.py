"""The order you work in (26 Oct): each time you start something other than what's planned right then, which kind you
chose over which. When one kind wins over another most of the time, Friday offers to plan it first (`kind_order`, the
kinds most important first). Pure: no database.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

MIN_CHOICES = 4  # times you chose one kind over the other before it's offered
SHARE = 0.75  # of the choices between the two
KEPT = 60  # the latest choices kept


@dataclass(frozen=True)
class Choice:
    chose: str  # the kind you started (a preset: Reading)
    over: str  # the kind planned then (Assignment)


@dataclass(frozen=True)
class OrderSuggestion:
    first: str
    then: str
    chose: int  # times you chose `first` over `then`
    of: int  # times you chose between them, either way


def suggest(
    choices: Sequence[Choice], kind_order: Sequence[str], refused: Sequence[tuple[str, str]]
) -> OrderSuggestion | None:
    """The kind you most clearly do first, over one `kind_order` doesn't already put after it; None until one wins
    `SHARE` of at least `MIN_CHOICES` choices. A pair you said no to isn't offered again."""
    counts = Counter((c.chose, c.over) for c in choices if c.chose != c.over)
    found = []
    for (first, then), n in counts.items():
        total = n + counts.get((then, first), 0)
        if n < MIN_CHOICES or n / total < SHARE or (first, then) in refused or before(kind_order, first, then):
            continue
        found.append(OrderSuggestion(first, then, n, total))
    return max(found, key=lambda s: (s.chose / s.of, s.chose), default=None)


def before(kind_order: Sequence[str], first: str, then: str) -> bool:
    """Whether `kind_order` already puts `first` ahead of `then`."""
    order = list(kind_order)
    return first in order and (then not in order or order.index(first) < order.index(then))


def reordered(kind_order: Sequence[str], first: str, then: str) -> list[str]:
    """`kind_order` with `first` just ahead of `then` (both added at the end when `then` isn't in it)."""
    order = [k for k in kind_order if k != first]
    if then in order:
        order.insert(order.index(then), first)
        return order
    return [*order, first, then]
