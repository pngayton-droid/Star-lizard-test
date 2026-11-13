# PRO STARLIZARD 2.0 — RECOVERY COVERING NOTE
**Checkpoint:** 2026-11-13
**Owner project:** pngayton-droid/Star-lizard-test
**Active development branch:** `starlizard-2-existing-data-only`
**Original production branch:** `main`
**Preservation branch:** `backup-before-interface-rebuild-2026-11-12`

## Read this first if a ChatGPT conversation goes read-only
The user wants a new, mobile-friendly football betting research app built using **only already-collected TheStatsAPI data**. API request allowance is running low: **do not trigger new provider API calls, historical collection or league imports** without approval. Do not use the old mixed-source research archive for model training. **DO NOT delete, revoke, rotate, overwrite or expose API keys, secrets, database records, collector scripts, GitHub Actions or schedules.** The user specifically corrected an earlier instruction: *do not wipe the keys*. Avoid modifying `main` until development is tested and user approves deployment.

## Latest implementation checkpoint (2026-11-13)
Commit `120d2b648985523efca3b9437787bc1f439d1e93`: Added a button-triggered, read-only per-league coverage audit in `starlizard_2.py` that joins match IDs across historical_xg, historical_match_odds and historical_match_events and counts full-time/halftime xG completeness. Includes CSV export. Does not fetch provider data. **Not yet live-tested**; audit reads existing database rows in paginated batches and can take time.

## Current implementation
- `starlizard_2.py` is a **new standalone Streamlit entry point** on the development branch. It reads Supabase tables `historical_xg`, `historical_match_events` and `historical_match_odds` using existing Streamlit secrets `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. No TheStatsAPI network requests.
- Shows existing-data totals, named league inventory, interactive league selector, match-count chart and research priorities.
- Header artwork `pro_starlizard_header_correct-1.png` reused from the existing repo.
- **Not deployed to production and not yet end-to-end tested.** Do not claim the scanner or profitable strategy exists.
- Development branch created from main; preservation branch captures pre-rebuild code.

## Database audit (2026-11-13, SQL against existing Supabase)
Project ID: `blokxfllmygudeucnhhb`. Table `historical_xg` contains 11,964 unique matches: 11,932 with competition ID and 32 without.
Counts by competition:
- comp_8321 Championship 1772
- comp_3039 Premier League 1557
- comp_5840 Serie A 1531
- comp_8814 La Liga 1529
- comp_0256 Ligue 1 1307
- comp_4643 Bundesliga 1237
- comp_8531 Belgian Pro League 950
- comp_3809 Eredivisie 935
- comp_8385 Primeira Liga 927
- comp_6387 Scottish Premiership 187
These are historical_xg counts, NOT guarantees of complete odds, xG or timelines. Historical events previously counted 11,932 rows; bookmaker market coverage is incomplete.

## User's goals
1. Use only TheStatsAPI as the source, no Understat mixed into new analysis.
2. Work within existing 10 stored leagues for now; consider lower divisions **only after** API requests refresh and user approves.
3. Find genuine, testable profitable edges, especially in-play and strong favourites falling behind; include original research ideas.
4. Develop fair-odds engine, historical backtester, league comparison, automatic match alerts, and mobile-friendly UI.
5. Avoid leakage: pre-match opening quotes cannot be traded based on later odds movement; live ROI requires contemporaneous live prices. Chronological holdouts and sample sizes mandatory.
6. Retain Scrumpy and Sally imagery and friendly app personality.
7. Regular GitHub recovery checkpoints **with a covering note** for future chat continuity.


### Research milestone — 2026-11-13
Created `research/strong_favourite_first_goal.sql` (commit `1874967b097407516eb419eeb4259c3d7a1b42da`). Reproducible read-only SQL for favourite below 1.50 by Bet365 `last_seen` match odds, opponent scoring the first non-own goal by minute 45. Executed against Supabase: **395 qualifying matches; favourite ultimately won 203, drew 95, lost 97**. League counts: EPL 67 (34 wins), Eredivisie 59 (34), La Liga 44 (27), Serie A 43 (26), Bundesliga 40 (18), Ligue 1 38 (17), Belgian Pro League 37 (16), Primeira Liga 35 (18), Championship 25 (11), Scotland 7 (2). **Exploratory only**, not an edge: last_seen price may not be pre-match, first-goal own goals excluded, VAR/timeline audit still needed, no in-play prices or ROI. These figures should not be advertised as verified live betting results.

### New build — halftime pattern explorer (2026-11-13)
Commit `bb62378eb9ce356004e842983f7135d15af2bdc6`: added fourth tab `HT research` in `starlizard_2.py`. It reads stored `historical_xg` in pages and filters by league, HT lead/draw state and HT xG leader. Reports descriptive counts and rates for home/away scored both halves, home/away won both halves, second-half draw, 2H 1+/2+ goals, FT home/away/draw, with CSV export. Removes incomplete and internally inconsistent score records. This is **multi-market descriptive research**, not a validated edge, fair odds model or live scanner. No TheStatsAPI requests. **Streamlit runtime smoke test still pending.**

### Independent SQL cross-check of halftime calculations
Read-only SQL against `historical_xg` returned **11,932 valid matches with nonnegative 2H goals and complete HT/FT scores**. Home scored in both halves: 3,474; away scored both: 2,527; home won both halves: 1,626; away won both: 911; second half draw: 4,124; second half 2+ goals: 5,544. These counts are full-archive descriptive checks, not app runtime test or evidence of profitability. SQL and Python definitions should be kept consistent.

### Chronological holdout module (2026-11-13)
Commits `ebd66b81ec57be3de4e4b20f9aa490dc36f4582b` and `a1fbeea5900d72ef527bb2abf99c89d73539b522`: added `research/chronological_validation.py` with whole-date train/test splits, Wilson confidence bounds, Brier score and a built-in self-test. Fifth dashboard tab provides league-specific chronological baseline evaluation for multiple historical HT/FT/second-half outcomes with CSV export. **Not yet run in the deployed Streamlit environment.** Attempted to download GitHub source to local container for syntax/smoke tests, but the container cannot resolve `raw.githubusercontent.com`. Do not claim tests passed; run `python -m py_compile starlizard_2.py research/chronological_validation.py` and `python research/chronological_validation.py` in an environment with the repo checked out, then Streamlit smoke test. This remains a baseline, not market-calibrated edge or live betting model.

### Bookmaker odds quality audit (2026-11-13)
Commit `f8c67f60fa2f5372d063e77c04a3c73c067d3bcf`: sixth tab `Odds quality` computes Bet365 match-odds 1X2 complete opening/last_seen quote coverage by league from stored odds JSON; read-only, CSV export, no provider calls. Independent Supabase SQL verified raw quote-presence counts (not price validation) by league: Championship opening 115 / last_seen 1771; Premier League 55/1556; La Liga 10/1525; Serie A 10/1521; Ligue 1 15/1302; Bundesliga 15/1234; Belgium 15/948; Eredivisie 15/930; Portugal 9/908; Scotland 15/185. **Opening quotes are extremely sparse. Last_seen timestamps not validated as pre-match closing. No live odds for ROI.** Dashboard counts may differ slightly because it rejects invalid numeric odds. Runtime testing pending.

### Pattern discovery and offline checks (2026-11-13)
- `starlizard_2.py` commit `0c318d2f81b5baae91f79b447730644f3eae9f15`: seventh tab searches league × HT score state × HT xG leader across ten outcomes, with a shared chronological train/test date cutoff and sample thresholds. Shows both training and held-out rates and Wilson intervals. Exploratory, not a confirmed signal; test-based sorting itself is selection bias, so a further untouched test period is mandatory.
- `tests/test_chronological_validation.py` commit `3dcdb97185bd207c761a74ab72534ccab344e96d`: regression tests for no same-date leakage, duplicates, training-only baseline and Wilson interval.
- `.github/workflows/starlizard2-research-tests.yml` commit `0febc706ceda3232cade2c9a0ce88a5a08ed2471`: automated syntax and no-network regression checks on pushes to development branch, and manual workflow dispatch. This workflow does not use provider credentials or Supabase. **Workflow execution status not verified**. Inspect GitHub Actions before claiming tests pass.

### Conditional model checkpoint (2026-11-13)
Added `research/conditional_model.py` (commit `6d37c1e5c1408e5e67df83a054b5392e0f6c89e5`): small-sample-smoothed categorical rates with a training-only global prior, prediction fallback for unseen feature combinations and held-out Brier scoring. Added eighth `Model check` dashboard tab (commit `c6fcb07580bef4dfcfdaafaf142f56c122d929be`) to compare chronological test Brier with a global training baseline, with user-selectable HT predictors. Added tests `tests/test_conditional_model.py` and expanded GitHub Actions offline check workflow. **These commits are untested in a live Streamlit runtime and Actions status has not been verified.** This is a predictive baseline, not a market-beating strategy. Critical next milestone: obtain reliable time-aligned bookmaker quotes for ROI validation, avoid repeated tuning on holdout, and verify runtime.

### Performance fix and checkpoint
Chronological holdout split now counts match dates in one pass and selects the nearest whole-date boundary without rescanning all matches per candidate (commits `811424574b88ee42a179f589e763f51a01410f74`, `37a7f5dd7ec4f747b24312ffb9a95fff3f0ace56`). This matters for roughly 12,000 stored matches. **Tests and Streamlit runtime have not yet been confirmed as passing.** No production changes, provider requests or data mutations.

### Research integrity fixes and three-period evaluation
Commits `210829e5647fc2d06367eaadd47e73be4c3412f9`, `34fc5ec1fe0f717c2d8eb3b309dd5bd4aa5c0adc`, `e6eed1568a9e765746311fdb7ffe2af3b0a9b14b`, `81ff0ad869c96bbbf2e4d3b3532fb10a36897957`, `6239419564d9a91cbb5492a463b5a696019c2bb7`:
- Reject fractional binary outcomes instead of silently truncating them.
- Rename the test-outcome-prevalence Brier comparator to `test_oracle_brier` (it used the test labels, so it is **not** a valid predictive baseline).
- Add whole-date 60% training / 20% validation / 20% final-test splitting, with regression tests.
- Change pattern search to use separate validation and final-test groups; rank by validation only. Subsequent commit `dd40aaf1de623a963f59fdada7693b2177f2c8cc` **withholds final-test outcomes** from the discovery table, reserving them for later one-time confirmation after candidate selection is frozen.
- Fix mismatch between renamed validation column and sorting key.
- No new provider requests or production changes. **Still awaiting verified automated test run and live Streamlit smoke test.**

### CI verification (2026-11-13)
Confirmed GitHub Actions run `43419737112` completed **successfully** at commit `55bf68d3d224b50c8df58ecb805042d2d91346d0`: syntax and offline research unit tests passed. URL: https://github.com/pngayton-droid/Star-lizard-test/actions/runs/43419737112 . Added a second job in workflow commit `53fcaee268633a545e4e3024b6448a209b7011b9` to install dependencies and verify the headless Streamlit HTTP health endpoint; this tests server startup only, **not authenticated Supabase queries or UI interactions**. At note time the new job was queued. Production remains untouched.

### Verified CI and preview hardening
GitHub Actions runs `43419990138` and `43420024196` both completed **successfully**, including headless Streamlit HTTP health check, offline unit tests and Python compilation. This is a verified **server startup**, not a full browser render or authenticated Supabase data test. Improved odds payload handling for malformed bookmaker objects and empty league inventory (commits `eb6cd11514281736b3f6c590680d85818d515ee1`, `eafa8e18869bcc45f8baa8f6e0f3365aca4bba9a`). Development branch only. No StatsAPI requests, production edits or credential changes.

### Offline UI integration test (2026-11-13)
Added `tests/test_streamlit_dashboard.py` using Streamlit `AppTest` and mocked Supabase fixtures; this makes zero external calls. Wired it into the dependency-installing CI job. First runs exposed two **test infrastructure** failures, not yet proven app failures: AppTest relative path resolved inside `tests/` instead of repository root, and GitHub Actions YAML folded two unittest commands into one shell line. Fixed via commits `61b61ec4fb44b55b2ddf0d1e52eb892b3e396bc4` and `3a9fea14a1f3f5623b409773b27d0c6c54f1ac2a`. Latest jobs pending verification. Do not claim fully rendered UI until AppTest job is green.

### Real stored-data integrity verification
Read-only Supabase SQL confirmed `historical_xg` has **11,964 rows**, all with match dates (2022-08-05 through 2026-11-03), **11,932 complete HT/FT score and HT xG rows**. All 11,932 complete-score rows have distinct match IDs, nonnegative second-half team goals, and non-null competition IDs. No TheStatsAPI requests were made. CI run `43421870215` completed **successfully** including Streamlit AppTest render, Python unit tests, and server startup. Expanded AppTest (commit `354f1a4160af12425ea0ab737c875b361ecc90f6`) to click coverage, halftime and bookmaker audit controls with mocked Supabase; status not yet confirmed. **Actual authenticated dashboard database access and Streamlit Cloud deployment remain unverified.**

### Model isolation and expanded UI coverage
GitHub Actions run `43422462577` was **green**, including click-through tests for coverage, halftime research and odds audit with mocked records. Subsequent commits `0811bc6d3a799f065fe44cf63dded20982a51e01` and `b95bb72fe0eff6fb6f93ed43be10a41819d485da` reserve the final chronological period without even filtering it for candidate group counts, and move the conditional model to train/validation/final-period separation. Commit `3da29bd1e066e8ba7cb983cc5a03c7442c9bea4a` expands UI test clicks to pattern search and conditional model. Latest CI pending verification. Existing production branch, provider keys and data unchanged.

### Mobile research summaries
GitHub Actions run `43425783567` completed **successfully** including extended model and pattern UI tests. Commits `9a07bcde1ae095451925ab3118e3c51c6c344f7a` and `b21f8d2f47e7268419a1201f4db58f38bfbc0728` add compact counts of eligible patterns and direction consistency, a Brier improvement metric against the global training baseline, and clearer mobile interpretation guidance. They do **not** establish a betting edge. New CI checks pending.

### Multiple-testing and split safety (2026-11-13)
GitHub Actions run `43426001834` **passed** with UI tests and mobile summary changes. Pattern discovery now reports how many candidate patterns passed thresholds and explicitly warns that Wilson intervals are unadjusted for multiple comparisons (commit `5bb44954e52fca008d14d8699f0b4e1c718c4888`). Three-way chronological split now gives a clear error when too few distinct match dates remain (commit `e115d04faaff57451d618d63217133bed8428c6e`) and has a regression test (commit `7f77ee3b40afb2ee9163e8723b038d33a2bbe364`). New CI pending. No final-test outcomes accessed during exploratory pattern selection. Still no time-aligned in-play prices, so no ROI claims.

### Integrity audit tab
CI run `43426479974` completed **successfully**. Added a ninth read-only `Integrity` tab (`54cb7c8aea18f8f805e81f1ed3696a7ab72a0294`) displaying completeness among score-consistent records and clearly warning that this does **not** audit goal timelines or VAR anomalies. Added a UI click-through test (`9f06160c0733738cda338237809c9192e3791c67`). New CI pending. Important limitation: this tab calls `halftime_research_data`, which excludes missing/inconsistent score records, so it is **not** an exhaustive raw-record audit; data coverage tab and independent SQL are needed for excluded-record counts.

### Raw integrity correction
After verified green GitHub Actions run `43436489852`, corrected ninth integrity tab to query **all** `historical_xg` rows, not just the filtered research subset. Commit `7ef0145978d913c477c41a1d32966ad9c9b276b9` now reports raw record count, duplicate IDs, incomplete scores, impossible second-half scores, missing dates, and missing halftime xG pairs. The prior limitation is superseded. CI pending. No source records modified.

### Raw integrity regression verification
GitHub Actions run `43436682141` **passed**, confirming the raw-integrity correction boots and its mocked UI runs. Added stronger AppTest fixture with a second deliberately incomplete record and assertions that the raw audit reports 2 records, 1 incomplete score, 1 missing date, and 1 missing halftime xG pair (commit `193c61fc61b25041495429cc592ae4ed4e2a9d8a`). Latest CI pending. No new provider calls.

### Score validation hardening
GitHub Actions run `43436941716` **passed**, including assertions for missing raw dates, scores and halftime xG. Commit `8deaaf5ecb1db181e8e4812bd0195ec966a47f65` now rejects negative and fractional score values from research outcome construction. Commit `70449724ba43b8faa4d4da9f8818ed5d29ad3427` exposes those anomalies in the raw integrity audit; `4de7307eee299b237e54bc77c025754fed1f0e23` adds an integration assertion. Latest CI pending. Production app and historical rows remain untouched.

### Validation baseline screen
GitHub Actions run `43437180492` passed after score validity hardening. Commit `0dd55edf7edfa1b6294e15a289671b594f245794` adds a conservative **exploratory** screen for whether each candidate pattern's validation Wilson interval excludes the global training-period event frequency. Shows the difference in percentage points and count of such patterns. Not adjusted for multiple testing, not odds-based, not ROI; final-test outcomes still reserved. New CI pending.

### Calibration diagnostics
GitHub Actions run `43437404262` **passed** for the validation-baseline screen. Added fixed-bin calibration analysis to `research/conditional_model.py` (commit `ea87cf786ecd56c7ce34d0e9530e671c2a64eca5`), a predicted-vs-observed validation table in the model tab (commit `130eb5951dd556a7a391fa7d3e4ef2118fd347f8`), and offline regression test (commit `fb2f72720c8c14065d62131a1bed374e4839c07b`). The table shows validation calibration only; no final-test peeking, no market-odds assumptions. CI pending.

### Additional malformed score fixture
Commit `fcc9623d5430cb995983a8856e26ca9717c6d92f` adds a synthetic fractional halftime score to the Streamlit AppTest fixture and asserts the integrity dashboard flags exactly one invalid score row. The historical research loader already excludes such records. Latest CI pending. No actual historical records altered.

## Immediate next steps
1. Verify syntax and run smoke test of `starlizard_2.py`, then repair any issues.
2. Build per-league data coverage diagnostics (join match IDs to odds and event tables, read-only).
3. Implement historical strong-favourite-falls-behind signal outcomes from verified timeline events, with proper goal order and anomaly exclusions.
4. Add actual out-of-sample probability calibration and pricing comparisons only where time-aligned odds exist.
5. Keep updating THIS NOTE with commit SHA, tested status, unresolved errors and next steps after each significant milestone. Create timestamped GitHub checkpoint branches after major working stages; do not claim automatic periodic backups unless an actual scheduler is configured.

## How to resume
Open the branch `starlizard-2-existing-data-only` in GitHub, read this file and `starlizard_2.py`, check the latest commits, then continue from the immediate next steps. Do not ask the user to recreate existing keys or data. Supabase and GitHub connector tools are available; read the installed Supabase skill before any Supabase task.

## Current status
**Implemented in code:** dashboard shell, league inventory and selector, per-league stored-data coverage audit and CSV export.
**Not yet implemented:** verified odds joins, favourite-trailing backtest, calibrated model, live quote ingestion, automatic alert scanner, deployment.
**Safety:** no database mutations or provider API calls were made during this checkpoint.
