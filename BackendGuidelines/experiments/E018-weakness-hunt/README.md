# E018 — Weakness hunt: instances built to break the v3 engine (P8)

**Question.** Where does the recommended engine (construction + sampler repair + CP-SAT deadline fallback + wall sampler) fail?
Each family targets one assumption: tight one-sitting packing (construction is greedy bin packing), tight deadlines with
2-hour minimum chunks (fragmentation), a 30-item dependency chain, 40 pins (locks everywhere), 2.2x overload (lateness is
unavoidable: quality of the overload path), and 150 items (speed).

**Engines.** `v3` (repair with CP-SAT fallback 5 s, then 5 s wall sampler), `v3_nocp` (repair by the sampler only), `cpsat30`.
Six seeds per family (tuning range), shared evaluator and checker.

**Metrics.** valid, late (vs best known), deadline-safe (zero late when zero is known possible), wellbeing/preferences gaps,
time; a catalogue of every failure with its cause.

**Hypotheses.** v3 is deadline-safe everywhere because of the CP-SAT fallback; v3_nocp fails on some one-sitting packing and
big-chunk instances; on overload CP-SAT-30 finds less lateness than the sampler path on some instances.
