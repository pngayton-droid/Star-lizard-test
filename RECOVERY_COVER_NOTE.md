# PRO STARLIZARD — recovery cover note (13 November 2026)

## Where the project lives
- GitHub source: https://github.com/pngayton-droid/Star-lizard-test (branch `main`).
- Supabase project ID: `blokxfllmygudeucnhhb`.
- Data source for the active model: TheStatsAPI only.
- GitHub Actions workflow: `.github/workflows/backup_supabase.yml`.
- Export code: `scripts/backup_supabase.py`.
- GitHub Actions artifacts expire after 7 days: download the database artifact and keep a separate private copy.
- Credentials are stored in GitHub Actions secrets, not in this note. Never share API keys.

## Current modelling decisions
- Independent pre-match 1X2 prices from a Poisson goal model.
- Strength model uses 50% xG + 50% actual goals as the fitting target, time decay half-life 240 days, ridge penalty scale 0.5.
- No venue-specific head-to-head adjustment in frozen predictions; historical H2H was tested and not consistently beneficial across leagues.
- Strict forward testing: 2025 and 2026 held out, training only before the validation cutoff.
- Do not alter the model simply to agree with bookmaker odds.

## Latest heavy-favourites audit
- Script: `research/audit_market_heavy_favourites.py`.
- Workflow: `.github/workflows/audit_market_heavy_favourites.yml`.
- Successful corrected audit run: https://github.com/pngayton-droid/Star-lizard-test/actions/runs/43520681013
- Across Premier League, La Liga, Bundesliga and Serie A, Bet365 last-seen favourites below 1.50: 455 qualifying matches in 2025–2026; actual win rate approximately 75.8%, frozen model mean approximately 63.6%.
- Interpret as a calibration warning, not a proven betting edge. Last-seen prices must be verified as strictly pre-kickoff.
- Opening odds exist for only a small fraction of collected matches; missing opening price must not suppress last-seen extraction.

## Data and recovery
- Database export workflow covers 11 public tables: historical_xg, historical_match_odds, historical_match_events, collector_progress, historical_xg_legacy_backup, starlizard_next_goal_research, archive_football_data, archive_source_links, archive_understat, archive_understat_goal_events, pattern_scan_history.
- Logical JSON export does NOT include PostgreSQL schema, indexes, policies, roles, database functions, triggers, auth users, storage objects, or GitHub secrets.
- Verify the backup workflow succeeded and download its artifact; do not assume the export exists merely because the workflow was triggered.
- Restore in a new Supabase project by recreating schema first and then importing table JSON with keys and foreign-key ordering considered. Test restore on a separate project before relying on it.
- GitHub repository remains the canonical code backup; make a separate private ZIP of the repo for offline protection.

## Next work after backup
1. Confirm full table counts and backup artifact.
2. Preserve a private off-platform copy of the code and data.
3. Diagnose heavy-favourite calibration (attack/defence shrinkage and strength estimates).
4. Test proposed correction strictly out of sample; do not retroactively tune to held-out matches.

## Restart instruction for a new ChatGPT conversation
'Continue PRO STARLIZARD from repository pngayton-droid/Star-lizard-test, Supabase project blokxfllmygudeucnhhb. Read RECOVERY_COVER_NOTE.md, the latest GitHub Actions logs, and the existing research scripts. Use TheStatsAPI only for active modelling, preserve stored data and secrets, and do not modify the model without forward validation. The next priority is diagnosing the 455-match heavy-favourite calibration gap.'
