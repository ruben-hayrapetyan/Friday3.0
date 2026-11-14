"""The start plan (DESIGN §11.6 step 1): items in earliest-deadline order, each into the earliest free slots.

Construction honors every wall: windows, the daily cap, minimum and maximum chunks (keeping legal remainders),
one-sitting runs and dependency readiness. Hard-deadline items take on-time slots first and spill into late ones
only when nothing else is left, so a plan with every hard item on time is a certificate that zero lateness is
possible. Elastic, target and open items start empty; the sampler places them.
"""

from dataclasses import dataclass, field

import numpy as np

from friday.engine.compile import Compiled, Model, compile_problem
from friday.engine.kernel import init_state, item_violations, new_state, total_violations
from friday.engine.problem import Problem
from friday.engine.prune import demote_locks

NO_DUE = 10.0**15


@dataclass
class Start:
    c: Compiled
    owner: np.ndarray
    violations: int  # wall violations left (0 = a valid start)
    demoted: list[str] = field(default_factory=list)  # items whose locks became preferred pins


def prepare_start(problem: Problem, base: np.ndarray | None = None, max_rounds: int = 3) -> Start:
    """Compile and construct; locks that leave violations become preferred pins and construction reruns."""
    demoted: list[str] = []
    for _ in range(max_rounds + 1):
        c = compile_problem(problem)
        owner = construct(c, base)
        st = new_state(c.m)
        init_state(c.m, st, owner)
        broken = [c.keys[i] for i in range(c.m.I) if st.item_violations[i] > 0 and c.m.locked[i].any()]
        if not broken:
            break
        demote_locks(problem, broken)
        demoted += broken
        if base is not None:
            base = remap_owner(base, c, compile_problem(problem))
    return Start(c, owner, int(total_violations(c.m, st)), demoted)


def remap_owner(owner: np.ndarray, old: Compiled, new: Compiled) -> np.ndarray:
    return new.owner_from_plan({k: v for k, v in old.plan_from_owner(owner).items() if k in new.keys})


def construct(
    c: Compiled, base: np.ndarray | None = None, only: set[str] | None = None, order: list[int] | None = None
) -> np.ndarray:
    """With `base`, a previous plan as owners, keep what it places where still allowed and add only what's missing;
    with `only`, add it only for those items; with `order`, place items in that order instead of by deadline."""
    M, problem = c.m, c.problem
    index = {k: i for i, k in enumerate(c.keys)}
    owner = np.full(M.S, -1, dtype=np.int16)
    day_units = np.zeros(M.D, dtype=np.int64)
    placed = np.zeros(M.I, dtype=np.int64)
    for s, key in problem.lock_owner.items():
        write(M, owner, day_units, placed, index[key], [s])
    if base is not None:
        keep_base(M, base, owner, day_units, placed)
        drop_invalid_kept(M, owner, day_units, placed)
    order = placement_order(c) if order is None else order
    # Elastic items too (meals, a 30–45 minute lunch): left for the anneal to grow from nothing, a narrow window
    # between classes was often never found and the meal was dropped. Hard items still come first.
    pending = [
        i
        for i in order
        if (M.amount_kind[i] == 0 and placed[i] < M.need[i]) or (M.amount_kind[i] == 1 and placed[i] == 0)
    ]
    if only is not None:
        pending = [i for i in pending if c.keys[i] in only]
    done: set[int] = set()
    for _ in range(4 * M.I + 10):
        if not pending:
            break
        for i in list(pending):
            if not sources_settled(M, placed, i, done, pending):
                continue
            place(M, owner, day_units, placed, i)
            done.add(i)
            pending.remove(i)
            break
        else:
            for i in list(pending):  # cyclic or blocked: place the rest in order anyway
                place(M, owner, day_units, placed, i)
                pending.remove(i)
    return owner


def keep_base(M: Model, base: np.ndarray, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray) -> None:
    for s in range(M.S):
        i = int(base[s])
        if i < 0 or owner[s] != -1 or not M.allowed[i, s]:
            continue
        # A 30-minute slot past the first week may end a quarter hour past what's needed (a 45-minute task fills an
        # hour there), as the kernel allows: kept to the need alone, the plan lost that slot, then the whole item
        # (too little of it), and every warm start moved it somewhere new.
        room = max(M.need[i], M.amount_cap[i]) + (1 if M.units[s] > 1 and M.amount_kind[i] in (0, 1) else 0)
        if placed[i] + M.units[s] <= room and day_units[M.day[s]] + M.units[s] <= M.day_cap[M.day[s]]:
            write(M, owner, day_units, placed, i, [s])


def drop_invalid_kept(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray) -> None:
    """A previous plan can break a wall once remaining work shrinks: start such items over (locks stay), and with
    them everything that waits on them, since their new place may come after what was kept."""
    st = new_state(M)
    init_state(M, st, owner)
    dropped = {i for i in range(M.I) if item_violations(M, st, i) > 0}
    grew = True
    while grew:
        waiting = {j for j in range(M.I) for d in range(M.dep_ptr[j], M.dep_ptr[j + 1]) if M.dep_source[d] in dropped}
        grew = not waiting <= dropped
        dropped |= waiting
    for i in sorted(dropped):
        for s in range(M.S):
            if owner[s] == i and not M.locked[i, s]:
                owner[s] = -1
                day_units[M.day[s]] -= M.units[s]
                placed[i] -= M.units[s]


def placement_order(c: Compiled) -> list[int]:
    """Hard items first, by effective deadline; a dependency source inherits its dependents' earliest deadline."""
    M, problem = c.m, c.problem
    due = np.array([problem.items[k].due_utc if problem.items[k].due_utc is not None else NO_DUE for k in c.keys])
    effective = due.astype(np.float64)
    for _ in range(M.I):
        changed = False
        for j in range(M.I):
            for d in range(M.dep_ptr[j], M.dep_ptr[j + 1]):
                source = M.dep_source[d]
                if effective[j] < effective[source]:
                    effective[source] = effective[j]
                    changed = True
        if not changed:
            break
    hard = [bool(M.hard_due[i]) or effective[i] < due[i] for i in range(M.I)]
    importance = [problem.items[k].importance for k in c.keys]
    # A meal's minimum first (COMBINED.md: personal pinned lunch): placed after the work, it found its window taken
    # by work due days later, and the anneal rarely moved both to give it back.
    meal = [M.amount_kind[i] == 1 and problem.items[c.keys[i]].min > 0 for i in range(M.I)]
    return sorted(range(M.I), key=lambda i: (0 if meal[i] else 1, 0 if hard[i] else 1, effective[i], -importance[i], i))


def fewest_late_order(c: Compiled) -> list[int]:
    """personal's start for an overloaded week (COMBINED.md 54): Moore–Hodgson on the hard items. In deadline order,
    whenever the work so far can't fit before the latest due, the longest task so far is set aside; the kept ones go
    first, in deadline order, so as many as can be are on time, and the set-aside ones fill what's left after them."""
    M, problem = c.m, c.problem
    deadline = placement_order(c)
    hard = [i for i in deadline if M.hard_due[i]]
    usable = M.allowed[:, : M.S].any(axis=0)
    ends = c.problem.grid.end
    kept: list[int] = []
    load = 0
    for i in hard:
        kept.append(i)
        load += int(M.need[i])
        due = problem.items[c.keys[i]].due_utc
        room = int(sum(int(M.units[s]) for s in range(M.S) if usable[s] and int(ends[s]) <= due))
        if load > room:
            longest = max(kept, key=lambda j: (int(M.need[j]), j))
            kept.remove(longest)
            load -= int(M.need[longest])
    rest = [i for i in deadline if i not in kept]
    return kept + rest


def sources_settled(M: Model, placed: np.ndarray, i: int, done: set[int], pending: list[int]) -> bool:
    for d in range(M.dep_ptr[i], M.dep_ptr[i + 1]):
        source = int(M.dep_source[d])
        settled = source in done or M.amount_kind[source] != 0 or placed[source] >= M.need[source]
        if not (settled or source not in pending):
            return False
    return True


def ready_conditions(M: Model, owner: np.ndarray, i: int) -> list[tuple[int, int]] | None:
    """Per dependency, the first slot from which i may start; None when a source is short."""
    out = []
    for d in range(M.dep_ptr[i], M.dep_ptr[i + 1]):
        source, required = int(M.dep_source[d]), int(M.dep_required[d])
        done, ready_at = 0, None
        for s in range(M.first_slot[source], M.last_slot[source] + 1):
            if owner[s] == source:
                done += int(M.units[s])
                if done >= required:
                    ready_at = s + 1
                    break
        if ready_at is None:
            return None
        out.append((d, ready_at))
    return out


def candidate_slots(M: Model, i: int, on_time_only: bool) -> list[int]:
    ok = M.on_time[i] if on_time_only else M.allowed[i]
    return [s for s in range(M.first_slot[i], M.last_slot[i] + 1) if ok[s]]


def place(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray, i: int) -> None:
    remaining = int(M.need[i] - placed[i])
    if remaining <= 0:
        return
    if M.one_sitting[i] and placed[i] > 0:
        extend_locked(M, owner, day_units, placed, i, remaining)
        return
    ready = ready_conditions(M, owner, i)
    if ready is None:
        return
    for on_time_only in (True, False) if M.hard_due[i] else (False,):
        candidates = [
            s for s in candidate_slots(M, i, on_time_only)
            if owner[s] == -1 and all(M.dep_lag[d, s] >= ready_at for d, ready_at in ready)
        ]  # fmt: skip
        remaining -= take(M, owner, day_units, placed, i, candidates, remaining)
        if remaining <= 0:
            return


def extend_locked(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray, i: int,
                  remaining: int) -> int:  # fmt: skip
    """A one-sitting item with locked slots grows out of its locked run instead of starting a second chunk."""
    held = [s for s in range(M.first_slot[i], M.last_slot[i] + 1) if owner[s] == i]
    got = 0
    for direction in (range(held[-1] + 1, M.S), range(held[0] - 1, -1, -1)):
        for s in direction:
            if got >= remaining or owner[s] != -1:
                break
            if not M.allowed[i, s] or day_units[M.day[s]] + M.units[s] > M.day_cap[M.day[s]]:
                break
            got += write(M, owner, day_units, placed, i, [s])
        if got >= remaining:
            break
    return got


def take(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray, i: int, candidates: list[int],
         remaining: int) -> int:  # fmt: skip
    """Write up to `remaining` units of item i into the candidate slots; returns the units written."""
    if M.one_sitting[i]:
        return take_one_sitting(M, owner, day_units, placed, i, candidates, remaining)
    taken, run = 0, []
    for s in [*candidates, -1]:
        if run and s != run[-1] + 1:
            taken += fill_run(M, owner, day_units, placed, i, run, remaining - taken)
            run = []
            if remaining - taken <= 0:
                break
        if s >= 0:
            run.append(s)
    return taken


def take_one_sitting(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray, i: int,
                     candidates: list[int], remaining: int) -> int:  # fmt: skip
    """The first run that holds the whole remaining amount within the day caps, or nothing."""
    run: list[int] = []
    for s in [*candidates, -1]:
        if run and s != run[-1] + 1:
            slots = prefix_holding(M, run, remaining)
            enough = remaining
            if M.amount_kind[i] == 1:  # elastic: as much as fits under its max, so coarse slots don't overshoot it
                while len(slots) > 1 and sum(int(M.units[t]) for t in slots) > M.amount_cap[i]:
                    slots = slots[:-1]
                enough = M.min_chunk[i]
            held = sum(int(M.units[t]) for t in slots)
            fits_caps = held >= enough and caps_allow(M, day_units, slots)
            if fits_caps and (M.max_chunk[i] < 0 or sum(int(M.units[t]) for t in slots) <= M.max_chunk[i]):
                return write(M, owner, day_units, placed, i, slots)
            run = []
        if s >= 0:
            run.append(s)
    return 0


def caps_allow(M: Model, day_units: np.ndarray, slots: list[int]) -> bool:
    added: dict[int, int] = {}
    for t in slots:
        added[int(M.day[t])] = added.get(int(M.day[t]), 0) + int(M.units[t])
    return all(day_units[d] + a <= M.day_cap[d] for d, a in added.items())


def prefix_holding(M: Model, run: list[int], units: int) -> list[int]:
    out, held = [], 0
    for t in run:
        if held >= units:
            break
        out.append(t)
        held += int(M.units[t])
    return out


def fill_run(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray, i: int, run: list[int],
             remaining: int) -> int:  # fmt: skip
    """Fill a run of consecutive free slots with chunks of legal size, one planning day at a time."""
    smallest, largest = int(M.min_chunk[i]), int(M.max_chunk[i])
    pieces, current = [], []
    for t in run:
        if current and M.day[t] != M.day[current[-1]]:
            pieces.append(current)
            current = []
        current.append(t)
    pieces.append(current)
    total = 0
    for piece in pieces:
        pos = 0
        while pos < len(piece) and remaining - total > 0:
            left = remaining - total
            room = int(M.day_cap[M.day[piece[pos]]] - day_units[M.day[piece[pos]]])
            # Work of its own right before (a lock, or the last chunk of the day before, as one planning day runs
            # into the next) joins this chunk: together they keep to the longest chunk. Joined past it, a lock you
            # could keep was demoted to a preferred pin.
            before = own_run(M, owner, i, piece[pos], -1) if largest >= 0 else 0
            if largest >= 0 and before >= largest:
                pos += 1
                continue
            chunk, units = [], 0
            for t in piece[pos:]:
                u = int(M.units[t])
                if units >= left or units + u > room:
                    break
                chunk.append(t)
                units += u
            if largest >= 0 and units > largest - before:
                chunk, units = cut_to(M, chunk, largest - before)
            if 0 < left - units < smallest:  # leave a remainder that is still a legal chunk
                chunk, units = cut_to(M, chunk, left - smallest)
            if chunk and largest >= 0 and before + units + own_run(M, owner, i, chunk[-1], 1) > largest:
                chunk, units = cut_to(M, chunk, units - int(M.units[chunk[-1]]))  # a free slot before what follows
            if units < smallest or not chunk:
                pos += max(1, len(chunk))
                continue
            total += write(M, owner, day_units, placed, i, chunk)
            pos += len(chunk) + 1  # a free slot between chunks keeps them from merging
    return total


def own_run(M: Model, owner: np.ndarray, i: int, t: int, step: int) -> int:
    """Units of item i's work right beside slot t, going back (step −1) or on (+1): what a chunk at t would join."""
    units, t = 0, t + step
    while 0 <= t < M.S and owner[t] == i:
        units += int(M.units[t])
        t += step
    return units


def cut_to(M: Model, chunk: list[int], limit: int) -> tuple[list[int], int]:
    out, held = [], 0
    for t in chunk:
        if held + int(M.units[t]) > limit:
            break
        out.append(t)
        held += int(M.units[t])
    return out, held


def write(M: Model, owner: np.ndarray, day_units: np.ndarray, placed: np.ndarray, i: int, slots: list[int]) -> int:
    for t in slots:
        owner[t] = i
        day_units[M.day[t]] += M.units[t]
        placed[i] += M.units[t]
    return int(sum(int(M.units[t]) for t in slots))
