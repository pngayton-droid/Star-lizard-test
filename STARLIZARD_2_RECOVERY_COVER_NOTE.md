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
