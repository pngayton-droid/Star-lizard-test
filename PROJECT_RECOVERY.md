# PRO STARLIZARD — Recovery checkpoint (2026-11-11)

## Where the project lives
- GitHub repository: https://github.com/pngayton-droid/Star-lizard-test (branch `main`)
- Streamlit app: https://pro-starlizard-preview.streamlit.app
- Supabase project reference: `blokxfllmygudeucnhhb`
- TheStatsAPI credentials are stored in deployment secrets; never commit them.

## Current implementation
- `pages/PRO_STARLIZARD_Dashboard.py`: central fixture queue, historical coverage, venue readiness, pre-match goal baseline, fixture-specific halftime scenario.
- `pages/Halftime_Pricing_Lab.py`: halftime historical frequencies and second-half scenario.
- `pages/Halftime_Intelligence.py`: single-variable and two-variable halftime research.
- `halftime_fixture_scenario.py`: explicitly uncalibrated Poisson second-half scenario and model-implied first second-half goal race.
- `test_halftime_fixture_scenario.py`: regression tests added, execution status not verified.
- `halftime_snapshot_pricing.py`, `halftime_interaction_engine.py`, `halftime_state_scanner.py`: historical research engines.
- `lightweight_fixture_feed.py`, `statsapi_recent_venue_xg.py`, `fixture_goals_baseline.py`: fixture and baseline data.

## Database
Supabase holds historical xG and match events plus imported archive tables. GitHub source control DOES NOT back up Supabase data. Previously created GitHub Actions encrypted archive artifact is time-limited and was not verified as a full database restore. Do not assume scheduled backup or comprehensive recovery without checking the workflow and artifacts.

## Priorities
1. Verify app deployment and automated test execution.
2. Connect real live halftime match state/xG and timestamped market odds; do not fabricate missing observations.
3. Verify next-goal sequences against event timelines, excluding suspect/VAR sequences.
4. Fit and calibrate fixture-specific halftime probabilities on training data; preserve untouched chronological validation data.
5. Integrate automatic opportunity ranking only after verified market quotes, costs, and calibration.
6. Implement and verify recurring encrypted database backups and restore procedure.

## Important safeguards
- Historical frequency and mechanical Poisson prices are NOT proven betting value.
- No automatic live odds, verified next-goal sequence model, or calibrated fair prices are claimed complete.
- All work should appear on the central mobile-first dashboard, with halftime the priority.
- Preserve credentials in secrets, never in the public repo.

## Starting a new conversation
Tell the assistant: "Continue PRO STARLIZARD from GitHub repo pngayton-droid/Star-lizard-test, read PROJECT_RECOVERY.md and inspect latest main commits. Work directly on GitHub and Supabase, keep halftime central, and don't ask me to test each small change."

## Progress checkpoint — 2026-11-11 (latest)

- Next-goal data audit `NEXT_GOAL_LABEL_AUDIT.md`: 6,948 trailing-at-HT matches; all second-half goal counts reconcile once `penalty_scored` is included. All 5,611 scored-match first-scorer labels agree with first timeline scoring event, including own-goal beneficiary; 1,337 no-goal outcomes verified. Separate 17 VAR suspect timelines still require follow-up.
- `halftime_next_goal_research.py` now supports unconditional three-way historical outcome frequencies, chronological match-date holdout, and frozen earlier-period three-way probability quality (multiclass Brier and log loss). Minimum 30 qualifying observations in each split; additive smoothing.
- `pages/PRO_STARLIZARD_Dashboard.py` now displays the three outcomes, earlier/later rates, and probability quality after the user requests research. `test_halftime_next_goal_research.py` has new tests; GitHub CI execution still needs verification.
- These are pooled conditional historical rates, **not** fixture-specific calibrated fair odds, verified positive expected value, or actual market quotes.
- Next: verify CI/deployment, compare holdout scores to honest pre-match baselines, reconcile the 17 VAR cases, then connect real live HT observations and odds.

## 2026-11-11 baseline comparison update
- Three-way chronological holdout now compares filtered trailing-team xG/location rates against an **earlier-only** unconditional reference trained on the same halftime deficit. Dashboard reports baseline Brier/log loss and flags filters with no Brier improvement. No later match outcomes enter either trained probability estimate.
- Regression assertions added for baseline arithmetic. GitHub combined commit status endpoint returned no statuses; this is **not** proof CI passed. Verify GitHub Actions separately.
- Remains research only: do not label value without market odds, out-of-time fixture-level calibration, and costs.
