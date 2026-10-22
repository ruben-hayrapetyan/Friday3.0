"""The 11 moves (DESIGN §11.7), built from `set_owner` so every total stays exact.

Moves only use slots an item may take (W2, and W9 for protected items) and never move a locked slot (W3).
Whether a move breaks W4–W8 is decided after it is applied, by re-counting the touched items' violations.
"""

import numpy as np

from friday.engine.kernel import (
    DROP,
    EJECT,
    FAR_SHIFT,
    GROW,
    INSERT,
    MERGE,
    SHIFT,
    SHRINK,
    SPLIT,
    SWAP,
    TRANSFER,
    kernel,
    set_owner,
)


@kernel
def may_take(M, protected, i, t):
    """W2, and W9 for protected items: a slot i may own."""
    if t < 0 or t >= M.S:
        return False
    if protected[i]:
        return M.on_time[i, t]
    return M.allowed[i, t]


@kernel
def pick_movable_slot(M, st):
    for _ in range(40):
        s = np.random.randint(0, M.S)
        o = st.owner[s]
        if o >= 0 and not M.locked[o, s]:
            return s
    return -1


@kernel
def chunk_around(M, st, s):
    """The unlocked run of slot s's owner around s (W3: locked slots never move)."""
    i = st.owner[s]
    a = s
    b = s
    while a - 1 >= 0 and st.owner[a - 1] == i and not M.locked[i, a - 1]:
        a -= 1
    while b + 1 < M.S and st.owner[b + 1] == i and not M.locked[i, b + 1]:
        b += 1
    return a, b


@kernel
def units_between(M, a, b):
    u = 0
    for t in range(a, b + 1):
        u += M.units[t]
    return u


@kernel
def fits(M, st, protected, i, c, U, va, vb, vc, vd):
    """The last slot e such that c..e holds exactly U units item i may take, or −1.

    A slot is available when it is free or inside a range being vacated (va..vb or vc..vd). Counting units, not
    slots, is what lets work cross into the 30-minute zone.
    """
    u = 0
    t = c
    while u < U:
        if t >= M.S or t < 0 or not may_take(M, protected, i, t):
            return -1
        o = st.owner[t]
        if o != -1 and not (va <= t <= vb) and not (vc <= t <= vd):
            return -1
        u += M.units[t]
        t += 1
    if u != U:
        return -1
    return t - 1


@kernel
def start_ending_at(M, e, U):
    """The first slot b such that b..e holds exactly U units, or −1."""
    u = 0
    t = e
    while u < U:
        if t < 0:
            return -1
        u += M.units[t]
        t -= 1
    if u != U:
        return -1
    return t + 1


@kernel
def end_piece(M, a, b, k, at_end):
    """The slots at one end of chunk a..b holding exactly k units, or (−1, −1)."""
    if at_end:
        start = start_ending_at(M, b, k)
        if start < a:
            return -1, -1
        return start, b
    u = 0
    t = a
    while u < k and t <= b:
        u += M.units[t]
        t += 1
    if u != k:
        return -1, -1
    return a, t - 1


@kernel
def clear_range(M, st, a, b):
    for t in range(a, b + 1):
        set_owner(M, st, t, -1)


@kernel
def fill_range(M, st, i, a, b):
    for t in range(a, b + 1):
        set_owner(M, st, t, i)


@kernel
def relocate(M, st, protected, i, a, b, c, touched):
    """Move item i's chunk a..b to start at c, keeping its units. Returns 1 when done."""
    e = fits(M, st, protected, i, c, units_between(M, a, b), a, b, 1, 0)
    if e < 0 or c == a:
        return 0
    clear_range(M, st, a, b)
    fill_range(M, st, i, c, e)
    touched[0] = i
    return 1


@kernel
def propose(M, st, protected, move, touched):
    """Apply one random move of the given kind. Returns how many items it touched (0 = nothing proposed).

    Moves only ever use slots an item may take (W2, W9) and never move a locked slot (W3). Whether a move
    breaks W4–W8 is decided after it is applied, by re-counting the touched items' violations.
    """
    if move == INSERT:
        return insert_chunk(M, st, protected, touched)
    s = pick_movable_slot(M, st)
    if s < 0:
        return 0
    i = st.owner[s]
    a, b = chunk_around(M, st, s)
    if move == SHIFT:
        return shift(M, st, protected, i, a, b, touched)
    if move == FAR_SHIFT:  # anywhere in the item's window
        c = np.random.randint(M.first_slot[i], M.last_slot[i] + 1)
        return relocate(M, st, protected, i, a, b, c, touched)
    if move == SWAP:
        return swap(M, st, protected, i, a, b, touched)
    if move == GROW:
        return grow(M, st, protected, i, a, b, touched)
    if move == SHRINK:  # the item loses one slot at either end; can break W6 or W7, which the chain rejects
        t = a if np.random.random() < 0.5 else b
        set_owner(M, st, t, -1)
        touched[0] = i
        return 1
    if move == TRANSFER:
        return transfer(M, st, protected, i, a, b, touched)
    if move == SPLIT:
        return split(M, st, protected, i, a, b, touched)
    if move == MERGE:
        return merge(M, st, protected, i, a, b, touched)
    if move == DROP:  # the whole chunk goes; can break W6 or W8 for dependents
        clear_range(M, st, a, b)
        touched[0] = i
        return 1
    if move == EJECT:
        return eject(M, st, protected, i, a, b, touched)
    return 0


@kernel
def shift(M, st, protected, i, a, b, touched):
    """Move a chunk 1–4 slots earlier or later."""
    step = np.random.randint(1, 5)
    if np.random.random() < 0.5:
        step = -step
    return relocate(M, st, protected, i, a, b, a + step, touched)


@kernel
def swap(M, st, protected, i, a, b, touched):
    """Swap two equal-unit chunks of different items. Both must be allowed where they land."""
    s2 = pick_movable_slot(M, st)
    if s2 < 0:
        return 0
    j = st.owner[s2]
    if j == i:
        return 0
    c, d = chunk_around(M, st, s2)
    U = units_between(M, a, b)
    if units_between(M, c, d) != U:
        return 0
    e1 = fits(M, st, protected, i, c, U, a, b, c, d)
    e2 = fits(M, st, protected, j, a, U, a, b, c, d)
    if e1 < 0 or e2 < 0:
        return 0
    if not (e2 < c or e1 < a):  # the two new ranges would collide
        return 0
    clear_range(M, st, a, b)
    clear_range(M, st, c, d)
    fill_range(M, st, i, c, e1)
    fill_range(M, st, j, a, e2)
    touched[0] = i
    touched[1] = j
    return 2


@kernel
def grow(M, st, protected, i, a, b, touched):
    """Extend a chunk by one free slot; can break W4, W5 or W7, which the chain rejects."""
    t = a - 1 if np.random.random() < 0.5 else b + 1
    if t < 0 or t >= M.S or st.owner[t] != -1 or not may_take(M, protected, i, t):
        return 0
    set_owner(M, st, t, i)
    touched[0] = i
    return 1


@kernel
def transfer(M, st, protected, i, a, b, touched):
    """Move k units from one end of a chunk to beside another chunk of the same item."""
    U = units_between(M, a, b)
    k = np.random.randint(1, 5)
    if k >= U:
        return 0
    ca, cb = end_piece(M, a, b, k, np.random.random() < 0.5)
    if ca < 0:
        return 0
    for _ in range(12):
        s2 = np.random.randint(M.first_slot[i], M.last_slot[i] + 1)
        if st.owner[s2] != i or M.locked[i, s2] or (a <= s2 <= b):
            continue
        c, d = chunk_around(M, st, s2)
        target = d + 1 if np.random.random() < 0.5 else start_ending_at(M, c - 1, k)
        if target < 0:
            continue
        e = fits(M, st, protected, i, target, k, ca, cb, 1, 0)
        if e < 0:
            continue
        clear_range(M, st, ca, cb)
        fill_range(M, st, i, target, e)
        touched[0] = i
        return 1
    return 0


@kernel
def split(M, st, protected, i, a, b, touched):
    """Cut a piece of at least the minimum chunk off a chunk and move it anywhere in the window.

    Essential: walls forbid breaking a long run one slot at a time (research report §5).
    """
    U = units_between(M, a, b)
    smallest = M.min_chunk[i]
    if 2 * smallest > U:
        return 0
    k = np.random.randint(smallest, U - smallest + 1)
    ca, cb = end_piece(M, a, b, k, np.random.random() < 0.5)
    if ca < 0:
        return 0
    c = np.random.randint(M.first_slot[i], M.last_slot[i] + 1)
    return relocate(M, st, protected, i, ca, cb, c, touched)


@kernel
def merge(M, st, protected, i, a, b, touched):
    """Move a chunk right before or after a sibling chunk of the same item."""
    U = units_between(M, a, b)
    for _ in range(12):
        s2 = np.random.randint(M.first_slot[i], M.last_slot[i] + 1)
        if st.owner[s2] != i or (a <= s2 <= b):
            continue
        c, d = chunk_around(M, st, s2)
        target = d + 1 if np.random.random() < 0.5 else start_ending_at(M, c - 1, U)
        if target < 0:
            continue
        if relocate(M, st, protected, i, a, b, target, touched):
            return 1
    return 0


@kernel
def insert_chunk(M, st, protected, touched):
    """Open a new chunk of a random item with room: its first-chunk units at a random free place.

    Essential for elastic, target and open items, which start empty.
    """
    i = np.random.randint(0, M.I)
    if st.placed[i] >= M.amount_cap[i] or M.last_slot[i] <= M.first_slot[i]:
        return 0
    t = np.random.randint(M.first_slot[i], M.last_slot[i] + 1)
    e = fits(M, st, protected, i, t, M.insert_units[i], 1, 0, 1, 0)
    if e < 0:
        return 0
    fill_range(M, st, i, t, e)
    touched[0] = i
    return 1


@kernel
def eject(M, st, protected, i, a, b, touched):
    """Move i's chunk onto a place one chunk of another item j holds, and move that chunk to a random place
    in j's window (or into the space i left). Locked slots of j are never displaced (W3)."""
    U = units_between(M, a, b)
    c = np.random.randint(M.first_slot[i], M.last_slot[i] + 1)
    j = -1
    u = 0
    t = c
    while u < U:  # the target: free, i's own chunk, or one other item's unlocked slots
        if t >= M.S or not may_take(M, protected, i, t):
            return 0
        o = st.owner[t]
        if o != -1 and not (a <= t <= b):
            if M.locked[o, t] or (j != -1 and o != j) or o == i:
                return 0
            j = o
        u += M.units[t]
        t += 1
    e = t - 1
    if u != U or j < 0:
        return 0
    s_j = c
    while st.owner[s_j] != j:
        s_j += 1
    c2, d2 = chunk_around(M, st, s_j)
    if c2 < c and M.locked[j, c2]:
        return 0
    for q in range(c, e + 1):  # every slot of j inside the target belongs to that one run
        if st.owner[q] == j and not (c2 <= q <= d2):
            return 0
    U2 = units_between(M, c2, d2)
    target = a if np.random.random() < 0.5 else np.random.randint(M.first_slot[j], M.last_slot[j] + 1)
    e2 = fits(M, st, protected, j, target, U2, a, b, c2, d2)
    if e2 < 0 or not (e2 < c or target > e):  # j's new place must not overlap i's
        return 0
    clear_range(M, st, a, b)
    clear_range(M, st, c2, d2)
    fill_range(M, st, i, c, e)
    fill_range(M, st, j, target, e2)
    touched[0] = i
    touched[1] = j
    return 2


@kernel
def add_dependents(M, touched, n):
    """Items waiting on a touched item need their W8 check redone too."""
    m = n
    for k in range(n):
        i = touched[k]
        for e in range(M.dependents_ptr[i], M.dependents_ptr[i + 1]):
            j = M.dependents[e]
            seen = False
            for q in range(m):
                if touched[q] == j:
                    seen = True
            if not seen and m < touched.shape[0]:
                touched[m] = j
                m += 1
    return m
