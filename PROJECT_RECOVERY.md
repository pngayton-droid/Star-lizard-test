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

## Full research-set integrity checkpoint — 2026-11-11
- Read-only Supabase reconciliation now verifies both first-half and second-half goal counts across all 11,581 `starlizard_next_goal_research` rows: **0 first-half mismatches and 0 second-half mismatches**, counting `goal`, `own_goal`, `penalty_scored`. Scoring-event sequence duplication across the full event archive: **0 duplicated match/period/sequence groups**.
- `NEXT_GOAL_LABEL_AUDIT.md` records the SQL-derived findings and limitations. Prior 17 VAR-suspect sequences are not yet separately resolved. Source-control checkpoint is not a database backup.

## CI hardening — 2026-11-11
- `.github/workflows/validate-halftime.yml` now triggers when `pages/PRO_STARLIZARD_Dashboard.py` changes, in addition to research/test module changes.
- Chronological holdout date selection excludes rows without a valid trailing-side designation; regression test added.
- GitHub commit workflow-run lookup returned an empty run list, which is not evidence of a passing or failing workflow; GitHub Actions UI or a run-specific API lookup still needs checking.

## Research cohort quality — 2026-11-11
- Supabase checked `starlizard_next_goal_research`: 11,581 rows and 11,581 distinct match IDs, date span 2022-09-18 through 2026-11-03. 6,948 trailing-at-HT rows; **0 missing trailing-team HT xG**.
- Chronological split cutoff now comes from the precise selected research cohort (HT deficit, trailing side, minimum trailing xG), not other matches. This reduces split distortion; separate regression test added. Holdout still uses simple historical frequencies, not fixture-level odds.

## Holdout input guard — 2026-11-11
- Chronological three-way research now rejects invalid trailing-side, halftime deficit, and minimum-xG filters before selecting split dates. Regression tests added.
- GitHub source commits are confirmed; automated test execution and deployment remain unverified. Next engineering priorities: run CI, resolve 17 VAR suspects by match ID, and build out-of-time fixture-level calibration against odds.

## Real chronological cohort result — 2026-11-11
- Direct Supabase evaluation of trailing by exactly one HT goal, trailing HT xG >=0.20: earlier n=2,383 (trailing-first 1,024), later n=1,146 (trailing-first 513). Date cutoff 2025-05-25.
- Earlier-trained conditional probabilities evaluated on later cohort: Brier 0.63355, log loss 1.04514. Earlier-only one-goal-deficit unconditional baseline: Brier 0.63637, log loss 1.04859. Small improvements +0.00283 Brier and +0.00344 log loss, not evidence of positive betting EV.
- Full methodology and counts in `NEXT_GOAL_LABEL_AUDIT.md`. Do not overclaim: no live odds, commissions, or prospective selection, and VAR cases remain outstanding.

## Product priority reset — user direction, 2026-11-11

**Primary objective: build the full PRO STARLIZARD football modelling platform. Do not get bogged down trying to find a single betting edge.** Historical strategy analysis is a supporting validation and automated-discovery feature, not the development roadmap.

Implementation order:
1. Central mobile-friendly dashboard, coherent navigation and useful match-level outputs.
2. Reliable StatsAPI ingestion, coverage, persisted historical data, scheduled updates and independently verified recoverable backups.
3. Reusable calibrated pricing modules: full-time goals, Asian handicap/totals, correct scores, halftime and next goal.
4. Opposition/venue-adjusted xG plus corners/cards/referee intelligence and forensic match dossier.
5. Actual live match-state ingestion, timestamped bookmaker/exchange quotes, comparison tools and automatically flagged evidence-backed signals.
6. Regression, chronology, data-quality and calibration tests continuously, but time-box research investigations; never imply a proven edge without prices and costs.

When user says "crack on", prefer concrete GitHub/Supabase engineering progress and commits over repeated narrow edge-hunting reports. Keep central dashboard integration a priority.

## Venue-stratified research — 2026-11-11
- One-goal HT trailing, HT xG>=0.20, chronological cutoff 2025-05-25: home trailing-first earlier 563/1,185 (47.51%), later 261/531 (49.15%); away earlier 461/1,198 (38.48%), later 252/615 (40.98%).
- Earlier-only add-one smoothed home probabilities trailing/leader/no-goal 0.47475/0.35354/0.17172; away 0.38468/0.41715/0.19817. Full counts in NEXT_GOAL_LABEL_AUDIT.md. Still need a side-aware baseline comparison and true market quotes.

## Dashboard-first engineering — 2026-11-11
- Main dashboard `pages/PRO_STARLIZARD_Dashboard.py` now includes a model-operations section: historical fixture coverage, venue-xG-ready fixture counts and percentage, explicit current capabilities vs future features, and a link to the fixture bridge.
- The match queue now offers a compact sortable table (fixture, competition ID, venue xG readiness, historical match count) and a downloadable CSV of all matching queue rows. Existing fixture details and halftime workspace remain.
- GitHub commits: `ddbbbd8d35db07f7b9f4ab7b7257b10fae190dcd`, `15deb125ef409f5e5edafc7ed9ea9a2a612375a8`. No deployment or automated-test success claimed without run evidence.
- Product objective remains integrated, trustworthy modelling platform, not a narrow strategy search.

## Reusable multi-market pricing module — 2026-11-11
- Added `fixture_market_pricing.py`: independently reusable Poisson research probabilities and decimal prices for 1X2, O/U 1.5 and 2.5, BTTS and top-eight correct scores. Reports unmodelled score-grid probability mass instead of silently normalising truncated results.
- Main `pages/PRO_STARLIZARD_Dashboard.py` now displays the multi-market research table and top-five correct scores for fixtures with a venue-xG baseline, using that shared module. These are **not calibrated fair odds** or verified market prices.
- Added `test_fixture_market_pricing.py` for symmetry, zero goals, analytic totals, input validation and score ranking. Updated `.github/workflows/validate-halftime.yml` to run new tests and compile module.
- Commits: `26b85a54078ea44b1d2bfdfcce6335d1ff3523ec`, `2ae46aa6b69ea9a2823c1563048fa5c8b13ca7c7`, `eff32ac2a50b31ee445e72b97611d704bb75e1d9`, `d048414f465ffe95542044bd2bb14b5184cd634a`. CI and deployment still need independent verification.

## Asian pricing integration — 2026-11-11
- Added `fixture_asian_pricing.py`: shared independent-Poisson Asian total and handicap settlement engine for quarter-goal increments. Outputs expected winning, losing, and refunded stake fractions and fair research decimal = 1 + loss/win, accounting for half-win/half-loss on split quarter lines.
- Central dashboard now displays selectable Asian totals, home handicap and corresponding away handicap with both sides' research prices and stake-win/push fractions.
- Added `test_fixture_asian_pricing.py` for integer pushes, quarter-line split, opposing handicaps, input validation; CI workflow includes module and tests.
- Commits: `8d8b4fe99b074f1da817e3e0075c887731443995`, `495110fb0dfea16fb74b5b445455b575372501a8`, `39863509f666878d5cb34346ddc6a17162617230`, `55c97f377407cccad9930b12adc3b0b027ef4e5e`. CI and deployment not independently confirmed.

## Fixture forensic dossier — 2026-11-11
- Added reusable `fixture_forensic_dossier.py`: matches historical home and away venue xG summaries by exact competition and normalized team name, includes sample count, xG for/against/difference, latest observation, and warnings for insufficient sample or stale/future dates.
- Main dashboard now displays a venue forensic table inside each venue-ready fixture before pricing. Explicitly labels venue aggregates as unadjusted and not a referee/corners/cards dossier yet.
- Added `test_fixture_forensic_dossier.py` and CI workflow entries. Commits: `929be35e970b8f9594b20e3912ee198a6560ca27`, `05292451433a913de18ea54771b7b4d9b654a046`, `f7c3a138193bd1a5b315053d8942d6743289a775`, `bdaec4458871b5c4eec052e6775826b196a0e078`.
- Code committed; successful CI execution and deployment still not independently confirmed.

## Mobile dashboard performance refactor — 2026-11-11
- `pages/PRO_STARLIZARD_Dashboard.py` now renders forensic dossier and multi-market research pricing for **one selected fixture**, rather than all (up to 80) expanded fixture cards on each Streamlit rerun. Queue table and CSV export remain intact.
- GitHub commits `0161e696c1c7dfb79af54c08eac8e44d08777810` and `fc68b309015a806e141aea61a26ee10b474a4ce5` (indentation correction).
- Attempt to run tests via public GitHub raw downloads in local container was blocked by DNS; do not claim tests or deployment passed. Need GitHub Actions run evidence or connector-based source materialization for independent test execution.

## Manual quote comparison — 2026-11-11
- Added `fixture_quote_comparison.py` for user-entered decimal odds and optional commission; computes expected net ROI and break-even decimal from settlement stake fractions (including Asian quarter-line half wins/losses/pushes). No real market feed, calibration or value alert.
- Integrated quote input and comparison into the selected fixture's pre-match dashboard pricing panel. Clearly warns that results are mechanical, uncalibrated scenarios.
- Added `test_fixture_quote_comparison.py` (fair even-money, commission, pushes, half wins/losses, invalid inputs) and extended CI workflow.
- Commits: `629c11b28c3bead5b9a6fdafb60e15f933f03107`, `abda4311ecf772c7b796d93bd2c507edbe0279f4`, `1581657e27bee2d1f7395777b29b5eb358e5701f`, `2278cd32ab6db231792561a483d37cd5e765ec43`. Test run and deployment still unverified.

## Pricing pipeline consistency tests — 2026-11-11
- Added `test_pricing_pipeline.py` checking independent-Poisson goals probabilities against equivalent Asian half-goal totals, and that each engine's own fair price produces zero expected return in the quote comparison module. Also checks Asian quarter-line settlement against the quote comparator.
- Extended central GitHub Actions regression workflow and renamed it to `Validate PRO STARLIZARD pricing` (file path unchanged).
- Commits `6e01f6e193dbc637ba66b3dcc022cfa7dd986ebb` and `1f98a2cf40193a05bc6166bcf06deff6dbe89d0d`. Tests committed, not independently confirmed passing; deployment not verified.
- Roadmap: engineering foundations exist but complete system needs API ingestion/refresh, data provenance, calibration, comprehensive forensic stats, live odds and match-state feeds, and independent end-to-end validation.

## Exportable fixture research snapshot — 2026-11-11
- Main dashboard selected fixture now offers downloadable versioned JSON containing fixture/date/competition, model identifier, baseline xG inputs and provenance, venue forensic dossier, 1X2/totals/BTTS/correct-score research probabilities and prices, selected Asian lines, and explicit model limitations.
- JSON snapshot is research-only and does not include a live bookmaker quote. Commit `0a10d462af5aa8b1c92656ed4e33e28f4cb9b269`. Deployment and automated tests remain unverified.

## Snapshot schema and reproducibility improvements — 2026-11-11
- Added `fixture_snapshot.py` pure schema-v2 research snapshot builder with UTC generation timestamp, fixture identity, provenance-labelled xG inputs, dossier, goals and Asian pricing, plus manually entered odds/commission and mechanical comparison. Explicitly warns venue summaries may be after selected date, so exports are **not point-in-time backtests**.
- Dashboard exports complete JSON **after** calculating manual quote comparison rather than before. Added `test_fixture_snapshot.py` schema/serialization checks and CI paths.
- Commits `912919a9c23603aeb9a4e6a1db8fda8900f1ae62`, `5d73b438ee9fbaf64906917fb1da63c440453d95`, `4b6b26bfc8ef464404c9d283887493c9bb0f5785`, `4e10a07dfe4d413c4df29451de4c53cd9ed46c60`. Test execution and deployment still unverified.

## Historical leakage safeguard — 2026-11-11
- Fixture JSON snapshots now explicitly compute `model.point_in_time_valid` by checking home/away venue summary latest dates against fixture date; future observations produce an extra warning and dashboard warning. This is only a preliminary leakage check, not a true point-in-time dataset reconstruction.
- Added regression cases for future and valid dates. Commits `a70699023ecf0cd0cfc56dc1273311e83ec7b664`, `d4e7ca8f584e391a5e2ea8ec5d2f7f9b009cd1bd`, `fde2ef2544c306deecb3b1b82dabd725a03acf43`. CI execution and deployment remain unverified.

## Strict fixture venue input audit — 2026-11-11
- Added `fixture_input_audit.py` to detect missing, ambiguous, malformed, low-sample and same-day/future-dated venue observations before showing research prices. The main dashboard suppresses pricing when known input provenance is unsafe, and explicitly notes that even eligible aggregates are not reconstructed point-in-time.
- Added `test_fixture_input_audit.py` and CI coverage. Commits `54a384491feec0377b94e61a62ba2ad939b290f5`, `29915ec7f940a3c2492fc0dd2b8f017305998abe`, `19c472f06ccfdfa58cd0228700c0d608e758d610`, `6b69446547d99e5d32c0c92e1dcfa1fa0bb763b4`. Tests/deployment unverified.

## Baseline input hardening — 2026-11-11
- `fixture_goals_baseline.py` now rejects malformed, nonfinite, and out-of-range source xG values before combining them, rather than letting NaN pass the previous range check and contaminate Poisson pricing.
- Added `test_fixture_goals_baseline.py` for normal inputs, NaN, infinity, malformed values, low samples and ambiguous team matching; CI includes the module and tests.
- Commits `643dfc6740b90f826e53adf1312685846ade5ae5`, `6ad3e7912eb6acd8bdc3ea7e9eade866930eae7b`, `51e4d08c0ee041557274e73d1b01a416de304a8d`. Test execution/deployment not independently confirmed.
