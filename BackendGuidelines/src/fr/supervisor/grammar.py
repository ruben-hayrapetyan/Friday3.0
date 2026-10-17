"""A small grammar of rule templates the supervisor may propose when the library cannot explain the rankings.

Every candidate is an ordinary reference rule type (here `time_preference`, the most general price rule), so a proposal
can be explained, edited and removed like any hand-written rule.
"""
from __future__ import annotations

DAY_SETS = {
    "weekdays": ["mon", "tue", "wed", "thu", "fri"],
    "weekend": ["sat", "sun"],
    "fri_sat": ["fri", "sat"],
    "mon": ["mon"], "tue": ["tue"], "wed": ["wed"], "thu": ["thu"], "fri": ["fri"], "sat": ["sat"], "sun": ["sun"],
    "all": None,
}
WINDOWS = {
    "early": ("06:00", "09:00"),
    "morning": ("09:00", "12:00"),
    "afternoon": ("12:00", "17:00"),
    "evening": ("17:00", "21:00"),
    "late": ("19:00", "23:59"),
    "night": ("21:00", "23:59"),
}
SCOPES = {"any": None, "deep": {"energy": "deep"}, "light": {"energy": "light"}}


def candidates(scopes: tuple[str, ...] = ("any", "deep")) -> list[dict]:
    out = []
    for dname, days in DAY_SETS.items():
        for wname, (a, b) in WINDOWS.items():
            for sname in scopes:
                d = dict(type="time_preference", name=f"cand:{dname}:{wname}:{sname}", weight=1.0,
                         params=dict(start=a, end=b, price=1.0))
                if days is not None:
                    d["params"]["days"] = days
                if SCOPES[sname] is not None:
                    d["scope"] = SCOPES[sname]
                out.append(d)
    return out


def matches_truth(name: str) -> bool:
    """Is a candidate the user's real missing preference (fri/sat evenings) or a close cover of it?"""
    _, days, window, scope = name.split(":")
    return days in ("fri_sat",) and window in ("late", "night", "evening") and scope == "any"
