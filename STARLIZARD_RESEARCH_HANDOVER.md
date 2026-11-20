# Pro Starlizard — research handover / cover note
Updated: 20 November 2026

## Read this first in a new chat
We are building **Pro Starlizard**, a football in-play research and pricing project. GitHub repo: `pngayton-droid/Star-lizard-test` (branch `main`). Supabase project ID: `blokxfllmygudeucnhhb`. Main data source is **TheStatsAPI**. Do not delete existing datasets, credentials, secrets, or dashboard pages. User prefers action over repeated confirmations, clear short progress reports, and copyable code blocks when instructions are necessary.

**Current priority:** Determine whether halftime expected goals (HT xG) improves forecasts of second-half goal counts, and whether that eventually translates into *genuine value* in live betting markets. User is interested primarily in **in-play** betting, not rebuilding another pre-match 1X2 model. There are **no historical Betfair halftime prices** available to us. Do not claim profitable betting results or an edge without genuine executable prices, commission, and realistic timestamping.

## Confirmed experiments (both passed their predefined statistical gate)
Two expanding-window, chronological Poisson-model experiments compared:
- **M0:** halftime home and away score + normalized implied probabilities from historical 1X2 prices.
- **M1:** M0 plus home and away HT xG.
- Target: joint second-half home and away goal counts; scored using paired joint Poisson negative log likelihood (log loss).
- Training starts after at least 1,000 earlier matches; evaluated month by month. Weekly block-bootstrap CI (3,000 draws). Gate: mean improvement >= 0.001, CI lower bound > 0, and positive yearly consistency (modern: >=4 positive years of >=3; archive: >=4 years).
- Lower log loss is better; reported *gain* = M0 log loss minus M1 log loss. These are **small improvements in statistical prediction**, **NOT ROI or proof of betting value**.

### Modern TheStatsAPI-era dataset
- Source: Supabase `halftime_research_outcomes` (12,028 records, dates 2022-08-05 to 2026-11-08), joined to `starlizard_backtest_1x2` on date + home team + away team.
- 11,994 usable matches; 10,812 held-out predictions.
- Mean joint log-loss improvement **+0.0018481008**, 95% weekly bootstrap CI **[+0.001567026, +0.002138640]**; 4/4 evaluated years positive; `pass_rule=True`.
- By year: 2023 2,234 matches +0.001908756; 2024 3,151 +0.002372084; 2025 3,269 +0.001707557; 2026 2,158 +0.001233116.
- Code: `scripts/audit_ht_goal_xg_modern.py`.
- Workflow: `.github/workflows/audit_ht_goal_xg_modern.yml`.
- Outputs: `research_results/ht_goal_xg_modern_summary.csv`, `research_results/ht_goal_xg_modern_yearly.csv`, `research_results/ht_goal_xg_modern_coverage.csv`.

### Older archive experiment
- Source: `archive_verified_match_research`, 6,182 rows, 2015–2022.
- 6,179 usable matches; 5,162 held-out predictions.
- Mean joint log-loss improvement **+0.0019243044**, 95% weekly bootstrap CI **[+0.001526972, +0.002347351]**; 6/6 evaluated years positive; `pass_rule=True`.
- By year: 2017 874 +0.002304361; 2018 869 +0.001761396; 2019 889 +0.001518605; 2020 862 +0.001972903; 2021 1,132 +0.001301600; 2022 536 +0.003478547.
- Code: `scripts/audit_ht_goal_xg.py`.
- Workflow: `.github/workflows/audit_ht_goal_xg.yml`.
- Outputs: `research_results/ht_goal_xg_summary.csv`, `research_results/ht_goal_xg_yearly.csv`, `research_results/ht_goal_xg_coverage.csv`.

## Important caveats — resolve BEFORE declaring a tradeable edge
1. **Odds provenance and timestamps not verified.** Modern data uses `home_price/draw_price/away_price` from `starlizard_backtest_1x2`; code labels these `b365_*` but the source bookmaker identity, whether opening or last-seen, and whether they existed before kickoff are not verified. Older archive odds similarly unverified. Audit source payloads and timing. Do not call these confirmed Bet365 opening or closing odds.
2. **HT xG may have been retrospectively revised.** Check whether it matches what could have been known at halftime. Postmatch revisions can create leakage.
3. **Halftime red cards omitted.** Explore `historical_match_events.timeline_data` and match IDs to derive red cards before HT, then rerun with a consistent control or exclude red-card matches.
4. **Model specification:** independent Poisson for each team's second-half goals, `PoissonRegressor(alpha=10.0)` after `StandardScaler`. Small log-loss gains might be sensitive to regularization or calibration. Do not tune on the same held-out test period and then report it as untouched validation.
5. **No real halftime market prices or Betfair exchange commission** were evaluated. Better predictive log loss is not sufficient evidence of positive expected betting ROI. There is no historical Betfair halftime price archive in the project.
6. Verify one-to-one historical match joins and source consistency, especially cross-league identifiers. The archive is a separate source from modern StatsAPI tables and must not be silently described as identical provenance.

## Suggested next steps
1. Audit the historical 1X2 odds bookmaker identity, opening/last-seen fields and actual timestamps; audit HT xG availability/revisions.
2. Check halftime red-card coverage and rerun a **predeclared** red-card-aware or no-red-card test, retaining all no-second-half-goal outcomes.
3. Examine which *specific second-half markets* benefit: over 0.5 / 1.5 / 2.5 second-half goals, next team to score, trailing team to score. Use strictly chronological training and future holdouts; calculate calibrated probabilities and fair odds, with uncertainty intervals.
4. Once a candidate survives validation, **log real in-play Betfair quotes prospectively** at a defined halftime timestamp, including available size, suspension state, commission and slippage. Verify actual Betfair/StatsAPI coverage before claiming a collector is active.
5. Compare predictions with real market prices; paper trade before considering stakes. Stop a hypothesis if no reliable advantage remains.

## What has NOT worked
Previous pre-match 1X2 strategies and historical-similarity approaches did not consistently outperform bookmaker pricing. Do not start another open-ended 1X2 calibration project without a new predeclared hypothesis. Similar-games/nearest-neighbour research is potentially useful for descriptive analysis, but no demonstrated profitable edge.

## Project working style
User calls assistant 'Neil' and sometimes 'bey'; prefers straightforward results, little interruption, and actual GitHub/Supabase execution when authorised. Preserve data and keys. Be explicit about what was run, what merely exists as a script, and what has not yet been verified. Never claim a workflow has completed without reading its results.

## How to resume
In a new ChatGPT conversation, say: **"Open `STARLIZARD_RESEARCH_HANDOVER.md` in my GitHub `pngayton-droid/Star-lizard-test` repository and continue the halftime xG in-play research from the next steps."**
