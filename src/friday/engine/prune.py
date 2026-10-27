"""Pruning (DESIGN §11.2, the first wall) and making locks usable. Pure: it only edits a Problem."""

from collections.abc import Iterable

from friday.engine.problem import Problem


def demote_unusable_locks(problem: Problem) -> bool:
    """A locked run that breaks its item's chunk rules and can't grow becomes a preferred pin."""
    grid, changed = problem.grid, False
    for item in problem.items.values():
        demote: set[int] = set()
        for run in locked_runs(item.locked):
            units = sum(int(grid.units[s]) for s in run)
            can_grow = any(n in item.allowed_set and n not in item.locked for n in (run[0] - 1, run[-1] + 1))
            too_short = units < item.min_chunk and not can_grow
            too_long = item.max_chunk is not None and units > item.max_chunk
            if too_short or too_long:
                demote.update(run)
        if demote:
            item.locked = frozenset(item.locked - demote)
            item.preferred = frozenset(item.preferred | demote)
            changed = True
    if changed:
        problem.refresh_locks()
    return changed


def locked_runs(locked: frozenset[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for s in sorted(locked):
        if runs and runs[-1][-1] == s - 1:
            runs[-1].append(s)
        else:
            runs.append([s])
    return runs


def prune(problem: Problem) -> None:
    """Remove every slot an item may never use (§11.2). Locked slots are always kept."""
    grid = problem.grid
    forbidders = [r for r in problem.rules if r.has_forbid]
    for item in problem.items.values():
        # Whether a rule applies is the item's, not the slot's: asked once a slot, it was most of a build (27 Oct).
        mine = [r for r in forbidders if r.applies(item)]
        release = grid.now if item.release_utc is None else item.release_utc
        keep = []
        for s in range(grid.S):
            if int(grid.start[s]) < release:
                continue
            if item.window_is_hard and item.due_utc is not None and int(grid.start[s]) >= item.due_utc:
                continue
            if problem.blocked[s] or problem.core[s]:
                continue
            if item.amount == "open" and problem.scales[grid.slots[s].day].open_value_slopes == 0:
                continue  # at growth 0 an open item is worth nothing that day, so it isn't placed at all
            owner = problem.lock_owner.get(s)
            if owner is not None and owner != item.key:
                continue
            if any(r.forbids(item, s) for r in mine):
                continue
            keep.append(s)
        item.set_allowed(keep)
    problem.price_cache.clear()


def demote_locks(problem: Problem, keys: Iterable[str]) -> None:
    """Turn the locks of `keys` into preferred pins and give their slots back to other items."""
    for key in keys:
        item = problem.items[key]
        item.preferred = frozenset(item.preferred | item.locked)
        item.locked = frozenset()
    problem.refresh_locks()
    prune(problem)
