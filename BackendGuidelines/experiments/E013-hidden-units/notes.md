# E013 notes — hidden units, and mood vs taste

Run: 3 user types (moody, easy, noisy) x 3 users x 16 weeks x 5 modes, each mode its own trajectory, 2 shards,
2026-10-17 12:59-14:13. (Planned 5 users per type; reduced to 3 when the shared machine needed its CPU back.)
`results/runs_shard*.csv` (per week), `final_inference_shard*.csv` (units re-read after all 16 weeks), `analyze.py`.
Easy and noisy users have a mood chain too, but their moods change nothing (mood_strength 0): any state Friday reads
there is a false attribution, and their check-ins report a mood that has no effect (a deliberately misleading signal).

## Results

| | none | dial (4 seeded units) | dial + 2 free | 6 free, no seeding | oracle (true mood) |
| --- | --- | --- | --- | --- | --- |
| moody: regret, median (95% CI) | 0.078 (0.056-0.107) | **0.051** (0.021-0.080) | 0.054 (0.017-0.078) | 0.061 (0.045-0.095) | 0.064 |
| moody: regret in weeks with a picked pace | 0.097 | 0.046 | **0.039** | 0.055 | 0.073 |
| moody: predictive log-lik of the week's rankings | -2.65 | **-2.28** | -2.42 | -2.54 | -1.85 |
| easy: regret | **0.049** | 0.085 | 0.085 | 0.051 | 0.078 |
| noisy: regret | 0.159 | **0.095** | 0.197 | 0.105 | 0.147 |
| weeks read as tired/motivated, easy users (all false) | - | 23% | 23% | - | - |
| weeks read as tired/motivated, noisy users (all false) | - | 42% | 31% | - | - |
| moody users: mood read right, all weeks (dial) | | 67% (32/48) | | | |

Moody users, dial mode, final reading vs truth: normal 22/27 right; motivated 6/10; tired 4/11 (tired weeks are mostly read
as normal). Per-user decision "state or noise" (cumulative predictive gain of dial over none > 2 nats): easy 3/3 noise,
noisy 3/3 noise, moody 2/3 state (the third, +0.9 nats, called noise): **8/9 right**.

## Against the hypotheses

1. **Partly.** Dial-seeded units cut moody users' regret by a third (0.078 -> 0.051, CIs overlap) but **cost** easy users
   (0.049 -> 0.085): with no state to find, the units chase the misleading check-ins (23% of weeks read as non-normal). So
   units must be switched on per user, by evidence (point 4), not by default.
2. **Mostly confirmed.** Free units without seeding never produce a nameable state (accuracy n/a), help moody users less
   (0.061) and are the safest for easy users (0.051) only because they barely move. Seeding is what makes the state usable.
3. **Confirmed.** Pace clamping is where the units pay off most (regret 0.039-0.046 in pace weeks vs 0.097 without units).
4. **Confirmed.** The predictive-likelihood test separates state from noise for 8 of 9 users; false attribution of single
   weeks is high (23% easy, 42% noisy), so a per-week reading must not change plans much unless the per-user test says
   "state" (RQ7).

Oracle's regret (0.064) is not the floor because its units use the PACE_H shape, which only approximates the true mood
effect (`MOOD_EFFECT`): knowing the mood is not knowing its effect.
