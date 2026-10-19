## 4. Representations and hard constraints (RQ1, RQ2)

**Four representations were built and measured on the same evaluator:**

| representation | what the state is | how hard rules are held | evidence |
| --- | --- | --- | --- |
| strict QUBO / Boltzmann machine | one binary unit per (item, slot) + slack bits | penalties: A for one-per-slot, B for amounts, deadline via price | E003 |
| slot assignment (Potts) + chunk moves, penalties | the owner of every slot | penalty lambda per violation; only violation-free states are returned | E004, E004b |
| slot assignment + chunk moves, **walls** | the owner of every slot | moves that would break a hard rule are rejected; items on time at the start are protected | E004, E005 |
| hybrids | as above | CP-SAT deadline skeleton then walls; walls then CP-SAT large-neighbourhood polish | E004 |

**The strict QUBO fails, and the failure is structural (E003).** On the slice of the problem a pairwise energy can express
(fixed-amount items with one-unit chunks and price rules only), single-flip annealing with the temperature tuned per instance
never met hard deadlines (0-5% of instances at any penalty scale, against 95% for the optimum). Below about 3x the largest
price the sampler cheats (it over-places items); above it the landscape freezes: the slack bits that turn "placed <= need"
into an equality absorb unplaced work, and leaving that state needs two coordinated flips across a barrier of about the
penalty itself. Plans were 25-200x the optimum. Everything else in the rule set (hinge measures, chunk rules, one-sitting
items, dependencies, the daily cap) needs helper registers per measure (hundreds per instance) with the same problem.
A Hopfield-style descent (T = 0) is no better. Figure: `report/figures/qubo_feasibility_vs_penalty.png`.

![QUBO](report/figures/qubo_feasibility_vs_penalty.png)

**Walls win on the guarantee; quality is close (E004, E005).** With the same moves and the same energy:

| 40 instances, 10 s | valid | deadline-safe | wellbeing gap (median) | preferences gap (median) |
| --- | --- | --- | --- | --- |
| walls | 100% | 100% | 0.000 | 0.000 |
| penalties (1e6 per violation) | 100% | 95% | 0.000 | 0.000 |
| CP-SAT skeleton + walls | 100% | 95% | 0.075 | 0.080 |
| walls + CP-SAT LNS | 100% | 100% | 0.050 | 0.044 |
| staged CP-SAT, 30 s budget (ran 61 s median) | 97% | 30% | 0.000 (8 comparable) | 0.42 (6) |

Penalties failed exactly where the start plan was itself late: walls let an unprotected late item only improve, while the
penalty chain spent its time in infeasible states and its best feasible state stayed late.

**Penalty scale on the full model (E004b, 20 instances, 5 s).** From the constructed start, walls were deadline-safe on 100%;
penalties of 0.1-1x the median move delta were cheated (wellbeing 2-7x worse, 95% safe); 10-100x behaved like walls on wellbeing
but left preferences 15-30% worse; deadlines as an ordinary weight (1x wellbeing) left avoidable lateness on 25% of instances.
From an empty plan every penalty variant missed 4.5-7 hard items (median) against 1 for walls: penalties neither keep nor find
feasibility reliably, which is the QUBO finding again on the full model. Figure: `report/figures/representations.png`.

![Deadline guarantee](report/figures/deadline_guarantee.png)

**The deadline guarantee (E005, 100 instances incl. adversarial families and stress).** Zero late work was known possible on
72 of them. EDF-order construction honouring every hard rule reached zero on 69/72 in under 32 ms; a short sampler repair on
the deadline stage alone fixed the other 3 (100%); the full wall sampler then never let lateness rise. CP-SAT's deadline stage
alone (15 s, 8 workers) found zero on only 51% (0/12 long dependency chains, 2/11 many-pins). On the 5 instances where
lateness is provably unavoidable, construction + repair was optimal on 3/5 and 1.5-3.7x the optimum on 2; CP-SAT hinted with
the repaired plan reached the proven optimum on all 5. On 23 overloaded instances with no proof either way, the sampler
path was at or below CP-SAT's lateness on 20 (typically 2-3x lower).

EDF ignores the daily cap, chunk minimums, one-sitting items and dependencies, so it said "feasible" on all 5 proven-overload
instances: it is a necessary-condition filter and a one-directional certificate, not the guarantee.

**So the guarantee is stated as:** an item that is complete and on time in the start plan can never become late (walls make
this monotone); the start plan is zero-late whenever construction + sampler repair + CP-SAT fallback find one, which was every
instance in this study where one exists. Overload (some lateness unavoidable) is handled by the same three steps, each keeping
the better plan; the remaining lateness is reported per item.
