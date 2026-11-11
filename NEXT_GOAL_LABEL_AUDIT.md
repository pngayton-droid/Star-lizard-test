# Next-goal label audit — 2026-11-11

Source: read-only queries against Supabase tables `starlizard_next_goal_research` and `historical_match_events`, joined on `match_id`.

- 11,581 next-goal research rows; 6,948 have a team trailing at halftime.
- Of trailing-team rows, 5,611 have a true/false first-scorer label and 1,337 have NULL.
- **All 1,337 NULL trailing-team rows have zero second-half goal or own-goal events** in the recorded timeline. NULL therefore appears to denote no second-half scorer for these rows, but further validation against final scores is required before declaring an exhaustive three-way label.
- Initially 284 labelled matches appeared to have zero second-half `goal` events. The feed also uses `own_goal`; counting both reduces the anomaly to **217** (131 labelled true, 86 labelled false).
- `own_goal` must be attributed to the beneficiary rather than the team responsible for the own goal when reconstructing first scorer.
- The 217 remaining labelled matches require event/score reconciliation before an unconditional next-goal market can be trusted.
- Prior audit separately identified 17 suspect VAR-related goal timelines; keep those excluded from sequence analysis until reconciled.

## Next implementation
Build a conservative match-level event verifier using `goal` and `own_goal`, correct own-goal attribution, halftime/fulltime score reconciliation, sequence ordering and excluded VAR duplicates. Compare verified first-second-half-scorer to stored labels and create a clearly enumerated outcome: home / away / no second-half goal / excluded. Only then compute fair odds, and validate by chronological holdout.

Do not present 2,674 / 5,611 labelled true outcomes as unconditional next-goal probability; the 1,337 goalless halves are excluded from that denominator.
