# Database backup and recovery checklist

**Current status:** GitHub saves source code on commit. A previous encrypted archive export was produced as a GitHub Actions artifact, but it was time-limited, covered only selected archive tables, and its restore was not tested. A scheduled full-database backup has NOT been verified.

## What must be protected
Supabase project `blokxfllmygudeucnhhb` currently has these ten public base tables:
- archive_football_data
- archive_source_links
- archive_understat
- archive_understat_goal_events
- collector_progress
- historical_match_events
- historical_xg
- historical_xg_legacy_backup
- pattern_scan_history
- starlizard_next_goal_research

Also protect views, SQL functions, grants/RLS, schemas, migrations, and relevant configuration. The historical match events and next-goal research tables are essential and must not be omitted.

## Before enabling automated exports
1. Verify Supabase's managed backup availability and retention in the project dashboard.
2. Configure a **separate** encrypted PostgreSQL backup to private off-platform storage. Do not upload raw SQL dumps to this public repository or unencrypted GitHub artifacts.
3. Use a read-only backup credential stored only in GitHub Actions secrets (or a trusted backup provider). Never put database URLs or encryption passphrases in source.
4. Schedule daily execution; verify artifact creation and retention, and alert on failures.
5. Perform a restore to an isolated test database and compare schema, table counts, and representative rows. A backup is not proven until a restore works.
6. Store an occasional independent copy outside GitHub and document the decryption key recovery procedure.

## Conversation recovery
Read `PROJECT_RECOVERY.md` and the latest commits on `main`. The app lives at https://pro-starlizard-preview.streamlit.app. Continue the unified dashboard, live halftime, verified next-goal events, calibrated probabilities, and real odds integration.

## Checks available now
`.github/workflows/validate-halftime.yml` runs probability regression tests and Python compilation checks on relevant changes. These are software tests, **not** proof of model profitability.
