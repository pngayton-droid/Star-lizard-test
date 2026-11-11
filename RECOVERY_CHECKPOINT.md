# PRO STARLIZARD — RECOVERY CHECKPOINT
Date: 2026-11-11 (UTC). Status: working development prototype, not a validated betting system.

## Primary locations
- GitHub source: https://github.com/pngayton-droid/Star-lizard-test (main branch).
- Streamlit deployment: https://pro-starlizard-preview.streamlit.app
- Supabase project reference: blokxfllmygudeucnhhb
- Private Supabase Storage bucket: starlizard-private-import
- Imported source object: starlizard_import_ready.zip
- TheStatsAPI subscription: active as reported by owner. Credentials are secret; never commit or paste them into a handover.

## Verified database checkpoint (2026-11-11)
- public.archive_football_data: 24,454 rows
- public.archive_understat: 16,442 rows
- public.archive_understat_goal_events: 39,811 rows
- public.archive_source_links: 6,182 rows
- public.pattern_scan_history: 1 saved snapshot
These figures were checked directly against Supabase. Source datasets overlap; do not sum match counts to infer unique matches.

## Main application pieces
- archive_data_engine.py — server-side read-only access to archive research and coverage views.
- pattern_intelligence_engine.py — deterministic exploratory outcome-rate scans with chronological holdout and false-discovery-rate adjustment.
- pattern_history_store.py — private scan snapshots, hash-based deduplication, history listing.
- pages/Archive_Historical_Research.py — linked-match archive research.
- pages/Archive_Data_Coverage.py — source, league and calendar-year coverage.
- pages/Automatic_Pattern_Scanner.py — exploratory goal/corner/card pattern scanner.
- pages/Model_Intelligence.py — unified data health and scanner findings, save/history controls.
- Additional existing pages cover forensic analysis, xG, Asian pricing, multi-league collection, and other research. Review repo before modifying.

## Supabase archive views
- public.archive_verified_match_research — 6,182 linked historical matches with odds/corners/cards/HT-xG fields.
- public.archive_first_second_half_goal — verified first goal after minute 45.
- public.archive_data_coverage — aggregated coverage by source/league/calendar year.
All private data access is server-side; views and history table should remain inaccessible to anon/authenticated roles.

## Research findings caveats
- A prior next-goal filter yielded 1,895 matches, 755 hits (~39.84%); no live next-goal market prices available, so profitability NOT established.
- The pattern scanner tests historical outcome-rate differences, not betting edges. Holdout is chronological, but is not a prospective validation; odds/fees and selection effects matter.
- Half-time xG timestamps are provisional; do not label them fully validated.
- Some imported cross-source links remain unresolved. Raw records were retained.
- One pattern scan snapshot was verified in the database on 2026-11-11; inspect it via Model Intelligence.

## Secure configuration
- GitHub Actions secret names previously used: STATS_API_KEY, SUPABASE_SECRET_KEY, SUPABASE_URL.
- Streamlit server secrets supply private Supabase access.
- DO NOT copy credentials into recovery docs, screenshots, public issues, or public GitHub commits.
- Repo is public. This document must contain no personal secrets or private match datasets.

## How to continue in a new chat
Say: "Continue PRO STARLIZARD. Read RECOVERY_CHECKPOINT.md in pngayton-droid/Star-lizard-test, inspect the current GitHub main branch and Supabase project blokxfllmygudeucnhhb, then continue building. Keep existing working pages intact. Make actual commits, verify changes, and explain one simple mobile step at a time."
Use connected GitHub and Supabase tools; do not rely on memory alone. Read the Supabase plugin skill before database work.

## Remaining roadmap
1. Compare saved pattern snapshots as new data arrives, including changed/disappeared signals.
2. Strengthen chronological and out-of-sample testing; avoid data leakage and spurious signals.
3. Integrate historical archive into pricing for goals/corners/cards/Asian markets only where sufficient reliable data exists.
4. Add live intelligence and market quote comparisons with appropriate timestamps and fees.
5. Unify navigation, mobile UX, observability and error handling.
6. Test end-to-end and create independent database and repository backups.

## Backup status — IMPORTANT
- GitHub repository is version-controlled but a single hosted copy is not an independent backup.
- The private source ZIP exists in Supabase Storage but this document is NOT a database dump.
- A full recoverable backup still requires a separate GitHub repository ZIP, a verified Supabase database export, and private Storage object export, saved outside their original services.
- Do not claim disaster recovery is complete until restoration from those exports has been tested.
