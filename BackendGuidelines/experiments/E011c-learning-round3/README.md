# E011c — Learning, round 3: fit the user's answer noise

**Why.** E011b: Bradley-Terry with a fixed temperature is the best learner on average but falls below no learning for noisy
users, as it treats every answer as almost certain. **Change.** `bt_auto` picks the temperature each week from {0.02 ... 0.5} by
3-fold cross-validated log-likelihood of the user's rankings so far. **Setup.** E011 protocol, learners none / combined / bt /
bt_auto (a third replicate for none, combined, bt). **Hypothesis.** bt_auto keeps bt's accuracy on easy, moody, missing and
adversarial users and recovers at least no-learning accuracy on noisy users; its fitted temperature separates noisy from easy users.
