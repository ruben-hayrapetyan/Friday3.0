# E017 — End-to-end semesters: v3 vs v2 (P8)

**Question.** Over full simulated terms, how does the recommended v3 system (wall sampler with tiered stages, Bradley-Terry
ranking learning with dial-seeded hidden units, a supervisor that proposes rules and picks which pairs to ask) compare with
the v2 baseline (staged CP-SAT at its 30 s budget, v2's max-margin learning from manual moves, paces as the only state)?

**Setup.** Report seeds only (instances from seed 10000, users from seed 20000; never used for tuning). User types easy, moody,
missing-feature, noisy; 3 users each; 12 weeks; a fresh Cornell-style two-week instance per week. Each system keeps its own
trajectory: it plans, the user lives the plan, drags, answers 6 pairs (chosen by the system: v3 picks by uncertainty, v2 has no
query policy so pairs are random), picks a pace in 30% of non-normal weeks, and the system learns. The v3 discovery threshold
comes from E014's tuning users.

Three systems: `v3` plans with one weighted energy (as the simulated users' own utility is a weighted sum and as Friday
learns it); `v3_lex` is the same system with tiered (lexicographic) stages, to separate the engine from the stage policy;
`v2` is lexicographic by design.

**Metrics.** regret against the plan optimised for the user's true weights and mood (relative); hard deadline misses and hard-
rule violations (must be 0); plan time; rules added (right/wrong); learned-weight cosine.

**Hypotheses.** v3: 100% valid, 0 avoidable misses, plans in ~2 s vs ~30 s, lower regret on moody and missing-feature users,
similar on easy and noisy users.
