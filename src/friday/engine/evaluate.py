"""The independent exact evaluator (DESIGN §11.12): stage values and per-rule totals of any plan.

Plain Python over section 12's definitions; the kernel must agree with it to the integer.
"""

from dataclasses import dataclass, field

from friday.engine.problem import STAGES, Plan, Problem, Solution
from friday.engine.pwl import measure_cost
from friday.engine.rules import BuildContext, price_row


@dataclass
class Evaluation:
    stage_values: dict[str, int]
    rule_totals: dict[str, int]
    rule_stage: dict[str, str]
    item_rule: dict[tuple[str, str], int]  # (rule, item) price costs only
    placed_units: dict[str, int]
    over_units: dict[str, int]
    late_hours: float
    overflow_hours: float
    deadline_misses: list[str]  # hard items due inside the horizon that are late or overflow
    measure_values: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.stage_values.values())

    def lex(self) -> tuple[int, ...]:
        return tuple(self.stage_values[s] for s in STAGES)


def evaluate(problem: Problem, plan: Plan) -> Evaluation:
    ctx = BuildContext(problem)
    solution = Solution(problem, plan, ctx.any_groups)
    totals: dict[str, int] = {}
    stage_of: dict[str, str] = {}
    item_rule: dict[tuple[str, str], int] = {}
    measure_values: dict[str, int] = {}
    for rule in problem.rules:
        total = 0
        if rule.has_price:
            for item in problem.items.values():
                if rule.applies(item):
                    cost = price_cost(problem, rule, item, solution)
                    if cost:
                        item_rule[(rule.name, item.key)] = cost
                    total += cost
        for m in rule.measures(ctx):
            value = m.expr.eval(solution.value)
            measure_values[f"{rule.name}/{m.name}"] = value
            total += measure_cost(m, value, rule.effective_weight, problem.scale, rule.name)
        totals[rule.name] = totals.get(rule.name, 0) + total
        stage_of[rule.name] = rule.stage
    stage_values = dict.fromkeys(STAGES, 0)
    for name, total in totals.items():
        stage_values[stage_of[name]] += total
    placed = {k: solution.placed(k) for k in problem.items}
    over = {k: solution.over(k) for k in problem.items}
    late_hours, misses = lateness(problem, solution, over)
    return Evaluation(stage_values, totals, stage_of, item_rule, placed, over, late_hours,
                      sum(over.values()) * 0.25, misses, measure_values)  # fmt: skip


def price_cost(problem: Problem, rule, item, solution: Solution) -> int:  # noqa: ANN001
    row = price_row(problem, rule, item)
    cost = int(sum(row[s] for s in solution.slots[item.key]))
    if item.amount == "fixed":
        cost += int(row[problem.grid.S]) * solution.over(item.key)
    return cost


def lateness(problem: Problem, solution: Solution, over: dict[str, int]) -> tuple[float, list[str]]:
    grid = problem.grid
    late, misses = 0.0, []
    for item in problem.items.values():
        if item.firmness != "hard" or item.due_utc is None or item.amount != "fixed":
            continue
        slots = solution.slots[item.key]
        hours = max(0.0, (int(grid.end[slots[-1]]) - item.due_utc) / 60) if slots else 0.0
        late += hours
        if item.due_utc <= grid.horizon_end and (hours > 0 or over[item.key] > 0):
            misses.append(item.key)
    return late, misses
