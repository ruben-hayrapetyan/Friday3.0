# E008 — Which moves matter (RQ4 move sets)

**Question.** The wall sampler proposes 10 move types: shift (1-4 slots), swap (equal-unit chunks of two items), grow, shrink,
transfer (k units between chunks of one item), split (cut a legal piece and move it), merge (next to a sibling chunk),
far shift (anywhere in the window), insert (new chunk), drop (remove a chunk). Which are needed, which are dead weight?

**Setup.** Single-thread geometric SA (the E007 baseline sampler), 4 s, reference n=40 and Cornell, tuning seeds 0-9
(20 instances). Variants: all moves; each move removed in turn (its probability set to 0); "minimal" = shift + far + insert +
drop only. Paired comparison per instance against "all".

**Hypotheses.** (1) Removing far shift or split hurts most (they are the only moves that spread work across days and break
long runs into legal pieces). (2) Swap and merge rarely matter (low acceptance in early runs). (3) The minimal set is clearly
worse, so chunk-reshaping moves (split, transfer) are what lets walls work with minimum-chunk rules.
