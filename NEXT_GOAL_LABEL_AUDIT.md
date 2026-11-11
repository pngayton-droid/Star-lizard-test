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

## Follow-up reconciliation — 2026-11-11

Joined `starlizard_next_goal_research` to `halftime_research_outcomes` on match date and both team names, and to `historical_match_events` on match ID. This is a research reconciliation, not a unique-key proof of every underlying match.

- **1,337 / 1,337** NULL first-scorer labels for trailing teams have zero second-half goals in BOTH the event timeline and the final-score-derived second-half totals. These are confirmed no-second-half-goal matches in this sample.
- **217 / 217** labelled matches with no second-half goal events nevertheless have one or more second-half goals in the final-score-derived totals. Their timelines are incomplete for first-scorer research and must be excluded.
- Of 6,948 trailing-team rows, **6,138** have equal second-half goal counts in the event timeline (including own goals) and final-score-derived totals; **810** do not match. The 810 includes the 217 completely missing second-half goal events.
- By stored first-scorer label, count matches: false 2,560 exact / 377 mismatch; true 2,241 exact / 433 mismatch; NULL 1,337 exact / 0 mismatch.
- Next-goal outcome research must distinguish verified no-goal from verified first-scorer, and exclude count mismatches. Even count agreement does not alone prove goal ordering or attribution: inspect event sequences and own goals before labelling a fully verified sample.
- Earlier audit of 17 suspect VAR timelines still requires exclusion/reconciliation.

**Do not use 2,674/6,948 as a verified unconditional hit rate.** The correct denominator for a verified three-way first-scorer analysis requires event-level consistency and ordering checks, not only final-score totals.

## RESOLVED — 2026-11-11: the 810 discrepancies were a counting bug

**Supersedes the earlier conclusion that 810 timelines were incomplete.** The reconciliation query omitted `penalty_scored` from goal event types. TheStatsAPI timeline has three scoring event types: `goal`, `own_goal`, and `penalty_scored`.

Re-ran the 6,948 trailing-at-HT match reconciliation against final-score-derived second-half goal counts, using all three scoring event types. **All 6,948 / 6,948 matched exactly, 0 discrepancies.** The 217 apparently missing timeline goals and the other 593 mismatches were artifacts of the incomplete query, NOT evidence of defective StatsAPI timelines.

All 1,337 NULL first-scorer outcomes correspond to verified no-second-half-goal matches. The 5,611 labelled outcomes are second-half goal matches. This resolves goal-count completeness in this trailing-team subset, **not** goal-sequence ordering, team attribution (especially own goals), the previously identified 17 VAR anomalies, or correctness of every row in the entire archive.

**Critical implementation rule:** When counting goals in timeline data, include `type IN ('goal','own_goal','penalty_scored')`. Do not treat `penalty_awarded`, `penalty_saved`, or `penalty_missed` as goals. Own goals must be attributed to the benefiting team when determining the next scorer.

The earlier sections above are retained as an audit trail; this resolution takes precedence.
