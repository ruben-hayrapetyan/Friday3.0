# E013b — Hidden units, round 2: gate them per user

**Why.** E013: dial-seeded units help moody users (regret 0.078 -> 0.051) but hurt users without moods (0.049 -> 0.085), and a
per-user predictive test told state from noise for 8/9 users. Drags now count 3x
(changed after E013 ran; the multiplicative link was already in E013). **Modes:** none, dial (always on), gated (the dial units are used only
once their cumulative predictive gain over taste-only exceeds 2 nats, or in a week the user picked a pace).
**Setup.** E013 protocol (moody, easy, noisy; 3 users each; 16 weeks). **Hypothesis.** gated keeps most of dial's gain for moody
users and none of its cost for easy and noisy users.
