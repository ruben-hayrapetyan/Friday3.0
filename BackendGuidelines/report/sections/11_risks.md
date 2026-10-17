## 11. Risks, limits and open questions

**What simulated users cannot tell us.**
- Real preferences may not be a weighted sum of the 18 reference features plus a few templates. The simulated users are, by
  construction, inside or one template outside the model; real users can be further out, and then every learner plateaus
  (missing-feature users in E011 show what that looks like). Discovery covers only `time_preference` templates.
- Real moods are not three states with fixed multipliers, real noise is not Bradley-Terry, and real users answer comparisons
  lazily, strategically or not at all. The learning numbers (E011-E016) rank methods; their absolute values will not transfer.
- Lived weeks were simulated as a short chain under the true energy from Friday's plan; real departures (illness, a missed
  bus) are not energy-driven, which is one reason likelihood learning from lived weeks should stay a weak regulariser.

**Statistical limits.** Learning experiments used 3 users per type (machine sharing forced the cut from 5); replicates
disagreed by up to 0.1 in accuracy for single cells (E011 vs E011b), so only differences that held across replicates are
claimed. Regret per week is a single-plan measurement with noise of roughly +-0.15 relative, so regret comparisons between
learners are mostly inconclusive; accuracy and weight recovery carry the learning conclusions. Engine comparisons used 10-40
instances per cell on tuning seeds; the final end-to-end comparison (E017) used report seeds only.

**Timing.** From session 2 the laptop was shared with a live service (load 10-190 on 16 cores) and all jobs ran at nice 19.
Comparisons ran interleaved and are fair, but absolute times are pessimistic, especially for 8-worker CP-SAT. The 548k
proposals per second and the reference targets should be re-measured on an idle machine before quoting them as product numbers.
Cold numba compilation takes ~66 s; a shipped engine must ship its compiled cache (or an ahead-of-time build).

**Engine risks.**
- The deadline guarantee rests on finding a zero-late start. Construction + sampler repair found one on every instance where one
  exists in this study (72/72), and the CP-SAT fallback covers the rest, but this is NP-hard in general (one-sitting items,
  minimum chunks). Keep the exact fallback and report the rare case it is used.
- Walls make lateness monotone only for items protected at the start; items that start late are optimised, not guaranteed.
- The kernel's exactness is enforced by tests against the shared evaluator; any new rule type must come with the same
  differential test or the guarantee "explanations are exact" breaks silently.
- DST is simplified away (a planning day is always 24 h).

**Open questions.**
- Per-user answer temperature: it detects noise (E011c) but using it inside the fit hurt moody users; a joint model of noise and
  mood is the natural next step.
- Faster state detection: the calibrated gate (E013c) is safe but slow; more evidence per week (skips and reviews with learned
  links, more check-ins) should speed it up, untested.
- Calibration of T > 0 probabilities against what users do (E010) depends on knowing the user's noise; see section 5.
- Interval (no-grid) CP-SAT (reference 6A.9) was not built; it might change the baseline's speed, not its staged design.
