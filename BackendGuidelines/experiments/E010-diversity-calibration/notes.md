# E010 notes — diversity and calibration of T > 0 samples

Run: 2026-10-17 16:13-16:17. `results/a_tiny_exact.csv`, `b_diversity.csv`, `c_user_calibration.csv`, `analyze.py`,
`figures/reliability_easy.png`.

## A. Does the chain sample the Boltzmann distribution? (tiny instances, every valid plan enumerated)

| T / median move delta | TV distance to exact p(x) | share of valid plans ever visited | exact probability mass never visited |
| --- | --- | --- | --- |
| 1 | 0.65 | 23% | 0.54 |
| 3 | 0.75 | 24% | 0.72 |
| 10 | 0.78 | 21% | 0.76 |

(medians over 10 instances, 3,300 valid plans median, 5,760 samples per run.)

**No, and the reason is reachability, not mixing time.** A follow-up on tiny-s0 (25,056 valid plans): a zero-energy walk that
accepts every valid move visited 3,930 plans with 50 steps between samples and 3,798 with 500, from 32,000 samples: more steps
do not reach more plans. The plans never reached are the most fragmented ones (for example an open item in three one-slot
pieces next to a target item in two pieces): getting there needs coordinated changes of several items in a nearly full grid,
which single moves under walls cannot make without passing through an invalid state. So **under walls the chain samples the
part of the valid set connected to its start**; its probabilities are probabilities over that component.

## B. Are T > 0 samples different plans? (reference n=40, 16 chains x 200k steps from an 8 s plan)

At every temperature tried (0.003-0.1 x median |delta|) the 16 samples differ in 66-71% of their work slots pairwise and give
each item 4.7-5.1 distinct day patterns (of 16); the two halves of the chains agree on item-day marginals to 0.035-0.041 (mean
absolute difference). They are meaningfully different plans. Caveat: the start plan came from the tiered scheme, which E006
showed is poor on preferences, so the chains *improved* on it (energy 600 points lower); diversity was measured while chains
also moved downhill, not at equilibrium around an optimum.

## C. Are "item X lands on day d" probabilities calibrated against a user? (easy and noisy users, 3 x 6 weeks)

| user type | T_f / user's tau | Brier score (climatology) | expected calibration error |
| --- | --- | --- | --- |
| easy | 0.3 | 0.0100 (0.078) | 0.0055 |
| easy | **1** | 0.0104 | **0.0026** |
| easy | 3 | 0.0107 | 0.0059 |
| noisy | 0.3 | 0.0231 (0.080) | 0.0163 |
| noisy | **1** | 0.0228 | **0.0090** |
| noisy | 3 | 0.0255 | 0.0113 |

Predictions from Friday's samples beat climatology by 3-8x and are best calibrated when the sampling temperature equals the
user's own choice temperature (hypothesis C confirmed); a too-cold sampler is over-confident (ECE x2 for easy, x1.8 for noisy).
Caveat: Friday used the user's true weights here; most item-day predictions are near 0 or 1 (items with tight windows), which
makes Brier scores small for every setting.

## Consequences

- Probabilities are usable for statements like "PS5 is very likely Tuesday" when the temperature is matched to the user's
  measured noise (E011c's fitted temperature gives it), with the caveat of A: they are probabilities over plans reachable from
  the current plan, not over all valid plans.
- An open improvement: a "rebuild item" move (clear an item and re-place its amount in random legal pieces) would connect
  fragmented regions of the valid set; untested.
