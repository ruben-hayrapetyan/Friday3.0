## 7. Hidden units, and mood vs taste (RQ6, RQ7)

**Model.** theta_eff = theta * exp(U h): hidden units rescale rule weights. The four v2 dials are the seeded units: capacity
lowers `daily_load` and `deep_run` weights, rest raises `late_night` and the reserves, spread raises `even_load`, growth raises
`open_value`, `target_shortfall` and `unscheduled`. The additive form E = sum (w + U h) phi was tried first; a planted-state
unit test showed theta's scale and the state trading off against each other (normal weeks read as "motivated"), so the
multiplicative form is the one recommended. A week's units are inferred (MAP) from that week's rankings, its skipped blocks
and a one-tap check-in; taste theta, free loadings and the evidence links are fitted jointly over all weeks. A picked pace
clamps the dial units.

**E013** (3 user types x 3 users x 16 weeks, each mode its own trajectory; easy and noisy users have a mood chain whose moods
change nothing, plus check-ins that report those moods, so any state read for them is a false attribution):

| | none | dial (4 seeded) | dial + 2 free | 6 free, unseeded | oracle mood |
| --- | --- | --- | --- | --- | --- |
| moody users, regret (median, 95% CI) | 0.078 (0.056-0.107) | **0.051** (0.021-0.080) | 0.054 | 0.061 | 0.064 |
| moody users, regret in pace weeks | 0.097 | 0.046 | **0.039** | 0.055 | 0.073 |
| easy users, regret | **0.049** | 0.085 | 0.085 | 0.051 | 0.078 |
| weeks read as non-normal (easy / noisy users: all false) | - | 23% / 42% | 23% / 31% | n/a | - |

- **Seeding matters.** Free units never yield a nameable state and help less (0.061); seeded units give a state the user can
  see ("Friday thinks you're tired this week") and the best regret for moody users.
- **Units have a cost when there is no state.** For easy users the seeded units chase misleading check-ins (23% of weeks read
  as non-normal) and regret rises from 0.049 to 0.085. So units must be switched on per user by evidence.
- **Pace clamping is the biggest single gain**: when the user names their state, regret halves.
- **Mood vs taste (RQ7).** A per-user test, "do the units predict next week's rankings at least 2 nats better (cumulatively)
  than taste alone?", called 8 of 9 users right in E013 (3/3 easy and 3/3 noisy as noise, 2/3 moody as state), but only 5 of 9
  in the replicate with the multiplicative link (E013b), for the reason given below. Single-week readings are unreliable
  (false attribution 23% of weeks for easy users, 42% for noisy ones).
  Evidence that separates them: predictive likelihood of new rankings (the decisive one), consistency of contradictions with
  check-ins and skip counts, and clustering of contradictions in time; noise is uncorrelated with all of them.
- Moody users' moods read right in 67% of weeks (normal 22/27, motivated 6/10, tired 4/11): tired weeks are mostly read as
  normal, which errs on the safe side (planning a normal week for a tired user) and is where the check-in and pace help.

**Gating, rounds 2 and 3 (E013b, E013c).** With the multiplicative link the simple gate ("units predict 2 nats better than
taste") opened for one easy and two noisy users: the units can win by shrinking the weights, which softens predictions and
fits noisy answers, without any state. Comparing instead with taste-only at its best answer temperature closed that loophole:
outside pace weeks the gated units cost mood-free users nothing (easy 0.069 vs 0.066, noisy 0.167 vs 0.167), but they recovered
only a quarter of always-on units' gain for moody users (0.119 vs 0.079 always-on vs 0.133 none): with 6 rankings a week the units
need many weeks to prove themselves. Always-on units replicated their E013 effect (moody 0.106 -> 0.065, easy 0.050 -> 0.095).

**Recommendation.** Dial-seeded units, multiplicative. Use them without proof only on explicit signals (a picked pace clamps
them; a one-tap check-in nudges them); automatic inference stays behind the calibrated gate (2 nats over taste at its best
temperature). This trades some regret for moody users for no harm to everyone else, which is the right default for a product.
Free units only after the seeded ones are on and pass the same test. Learning hidden units with no dial seeding (section 8 of
the prompt) is a dead end for a product: no nameable state, slower, no gain. Figure: `report/figures/hidden_units.png`.
