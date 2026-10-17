# E013c — Hidden units, round 3: a gate that temperature alone cannot open

**Why.** E013b: the per-user gate opened for users without moods because the units also act as a temperature knob. **Change.**
The gate compares the units' cumulative predictive log-likelihood with that of taste-only evaluated at its best answer
temperature in hindsight (grid 0.02-0.5, the E011c noise estimate), and needs a 2-nat margin. **Setup.** E013 protocol;
modes none, dial, gated2. **Hypothesis.** gated2 opens for moody users only, so it keeps dial's gain for them and costs easy and
noisy users nothing.
