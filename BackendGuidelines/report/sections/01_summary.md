## 1. Summary and recommendation

**Recommendation.** Rebuild Friday's engine as an **energy sampler over the slot grid with walls**, not as a Boltzmann machine
with penalties and not as v2's staged CP-SAT. The state is the owner of each slot; the energy is exactly v2's rule set, computed
incrementally by a compiled kernel that equals the shared evaluator to the integer; hard rules are **walls** (moves that would
break one are never taken); the start plan comes from an earliest-deadline construction that honors every hard rule, a short
sampler repair, and a CP-SAT deadline fallback for the rare remainder. Plans are found by simulated annealing with chunk-level
moves, one chain per idle core, with a fixed step budget. Weights are learned from rankings and drags by a Bradley-Terry
likelihood; the four dials become hidden units that only act on explicit signals until they prove themselves; a supervisor
routes feedback, proposes missing rules for the user to accept, never softens a "never" rule silently, and chooses which
comparisons to ask. Section 12 specifies it.

**Against v2, on the same evaluator** (E017: report seeds, 144 simulated user-weeks per system; E004/E005: 40-100 instances):

| claim | evidence | confidence |
| --- | --- | --- |
| v3 never breaks a hard rule and never misses an avoidable deadline; v2 does both | E017: 0/288 vs 5/144 weeks with a miss or an invalid plan; E005: zero late on 72/72 instances where possible (v2's deadline stage alone 51%); E004: 100% vs 30% deadline-safe | high |
| v3 is about 15x faster on weekly plans and 9-27x on warm replans | weekly plan 1.3 s vs 19.8 s median (E017); warm replan 0.9-2.7 s vs 24 s (E009b); meets the reference's cold (<= 10 s) and warm (<= 3 s) p90 targets, which v2 misses by 2-9x (E001) | high (absolute times measured on a loaded laptop, pessimistic for both) |
| v3's plans are better | regret 0.087 vs 6.13, lower in 144/144 user-weeks (E017); with v2's own lexicographic stage policy still better in 78% of weeks; ties or beats CP-SAT-30 s on every comparable stage at 2-10 s (E004, E007) | high for the engine; the size of the gap depends on the stage policy (below) |
| v3 learns preferences better | learned-weight cosine 0.955 vs 0.866 (E017); held-out ranking accuracy 0.85-0.87 vs 0.82 for v2-style learning, but replicates vary by up to 0.1 (E011-E011c) | medium |
| v3 finds preferences the rule library lacks; v2 cannot | right rule for 6/6 evaluation users by week 4 (E014) and 3/3 semester users (E017); no wrong rule accepted when proposals need the user's yes | medium (one kind of missing rule tested) |
| hidden "mood" units help | 30-40% lower regret for moody users when always on, but 30-60% higher for users without moods; a safe gate keeps only a quarter of the gain (E013-E013c) | medium; use explicit signals (paces) |

**Where v2 is still better.** Given its full 30 s and a good hint, CP-SAT finds lower wellbeing on more warm replans (about 60%
of instances in E009/E009b) and v2's warm replans moved slightly less work before v3's stage scheme was fixed. v2's plans are
optimal for its deadline stage when CP-SAT proves optimality (overload): v3 keeps CP-SAT for exactly that case. And on tight
overload weeks packed with 2-hour minimum chunks, CP-SAT at 30 s on 8 fast cores still finds less lateness (best on 6/6 vs 3/6
for v3's 5 s fallback on efficiency cores, E018d); v3 should give its fallback more time in an overload week.

**The biggest open decision is not the engine but the stage policy.** Strict "wellbeing first, then preferences" costs simulated
users far more than the engine choice does (v3 lexicographic 1.6 vs weighted 0.09 regret); real users may want it anyway. v3
supports both; the recommended default is "lexicographic in effect, weighted in search" (weighted 1000:1 search, then a
preference polish that cannot raise wellbeing).

**What failed** (section 10): the strict QUBO/Boltzmann machine (never deadline-safe at any penalty scale; it cheats or freezes),
penalties instead of walls, an RBM learned from lived weeks without rules, learning from likelihood alone, always-on hidden units,
and asking noisy users many questions.

**Answers to the research questions** (details in the sections named):

| RQ | answer | where |
| --- | --- | --- |
| RQ1 representation | Slot assignment (Potts) with chunk-level moves and walls. The strict QUBO cannot express most rules and fails on the rest; penalties on the full model cheat or cost quality; CP-SAT hybrids (skeleton, LNS) cost more time than they save | 4 |
| RQ2 hard constraints | Walls + EDF-order construction + sampler repair + CP-SAT fallback: zero late on 72/72 instances where possible and every evaluation week; EDF alone is a one-directional test; overload goes through the same three steps, with CP-SAT exact on proven cases | 4 |
| RQ3 stages | Weighted 1:1-10:1 disagrees with the lexicographic answer on 85-100% of instances; 1000:1 on 20% (by <= 3%); strict tiers lose 3x on preferences; recommended: weighted 1000:1 search + capped preference polish | 5 |
| RQ4 samplers and speed | Geometric Metropolis SA with 11 chunk moves (split essential), multi-start on idle cores (as good as PT), tabu finish; 550k moves/s; 2 s matches CP-SAT-30 s; warm replans < 1 s | 5 |
| RQ5 learning | Bradley-Terry likelihood over rankings and drags (drags x3) beats the ranking QP, CD, PCD and v2's moves-only max-margin on average and under deliberate inconsistency; likelihood from lived weeks alone barely learns | 6 |
| RQ6 hidden units | Dial-seeded, multiplicative units; they help moody users (-30-40% regret) and hurt the rest (+30-60%) when always on; use on explicit signals (paces) and behind a temperature-calibrated gate | 7 |
| RQ7 mood vs taste | Decide per user, not per week (single weeks: 23-42% false attribution); the decisive evidence is predictive likelihood of new rankings against a baseline at the user's own answer temperature; without that calibration units win by softening predictions | 7 |
| RQ8 supervisor | Missing rules: the right rule is the top candidate for every tested user by week 12 (6/6 evaluation users already at week 4); propose, add on yes (no wrong rule accepted). Walls: never soften silently; ask once. Queries: QBC/uncertainty halve questions for consistent users; stop asking noisy users | 8 |
| RQ9 guarantees | Determinism with a fixed step budget (all warm reruns identical; independent of thread count); exact per-rule explanations and "why not elsewhere" (tested to equal the evaluator); churn about equal to CP-SAT-30 s with the recommended stage scheme | 5 |
| RQ10 diversity and calibration | T > 0 samples are different plans (66-71% of work slots differ); item-day probabilities calibrated (ECE 0.003-0.009) when T matches the user's noise; but under walls the chain covers only the region reachable from its start (~20% of all valid plans on tiny instances), so it is not a full posterior | 5 |

**Program 2** (section 14; spec in 15): the engine behind the Friday app's Planner page. As shipped, it learns task lengths
from the user's estimates and recorded times, plans hard deadlines at the 95th percentile, asks at most two "how long did
it take?" questions a week, offers three schedules ranked so that the recommended one is the likeliest pick, learns from
the pick, and takes constraints in plain language through Claude Sonnet 5.5 (99% of held-out texts read right). In a
simulated six-week term it misses 8.8% of hard deadlines vs 67.5% for v3 as built, and schedules almost no work
against the person's real habits (0.08 vs 7.8 h a week).

