# New Scanner — handover note
**Saved:** 20 November 2026  
**Project:** THE MATCH MATRIX / PRO STARLIZARD  
**Repository:** `pngayton-droid/Star-lizard-test` (main branch)

## Resume instruction for a new ChatGPT conversation
"Continue the **new scanner** work in my GitHub repo `pngayton-droid/Star-lizard-test`. Read `NEW_SCANNER.md`, `pages/94_Quick_Halftime_Scanner.py`, `pages/95_Half_Time_Fair_Odds.py`, and the relevant data/API helpers first. Keep our existing model, keys, database and old dashboard intact. Focus on a genuinely automatic, compact mobile-first halftime scanner. Verify changes and do not claim deployment success without testing."

## Why we are rebuilding the interface
On 20 November, handling only four matches was awkward: many manually entered halftime statistics and pre-match prices, long scrolling on a phone, and an odds snapshot table reporting `APIError`. The user wants a one-screen, multi-match scanner that displays fair odds without typing 15 inputs per match. Avoid further cosmetic tweaks that leave the core manual workflow unchanged.

## What is committed and working so far
- **New page:** `pages/94_Quick_Halftime_Scanner.py` — The Match Matrix, compact mobile-first scanner.
- **Old page:** `pages/95_Half_Time_Fair_Odds.py` — preserved, now links prominently to the new page via `st.page_link`.
- The scanner lists fixtures in ten selected leagues, offers All / Half-time-live / Finished filters, a collapsible fixture list and a match selector.
- The user confirmed in Streamlit screenshots that the page deployed and displays four fixtures on 20 November 2026.
- The `Fetch first-half stats` button successfully calls TheStatsAPI's `/football/matches/{id}/stats` endpoint for Bayern München v Köln.
- **10/10 first-half statistics recognised and populated** after fixing Streamlit session-state widget hydration. These are home/away first-half xG, shots, shots on target, corners and red cards.
- No guessed placeholders: fair odds are withheld when required data is missing.
- Existing deployed trained halftime model is used for fair prices once all required inputs are present; it is NOT replaced by the separately trained retrospective research model.
- Last scanner commit at handover: `0b69cca5a1a919a5cdb9405f5f1787f08ee75e2d` (autofill verified halftime score and stored pre-match odds).

## Confirmed outstanding blocker: five missing inputs
In the latest screenshot (22:35 UK time, 20 November), the scanner still shows **"Missing 5 verified inputs. No fair prices calculated."**
- **Two:** verified home/away half-time goals. The fixture's current score is not necessarily its halftime score. Current code checks explicitly labelled halftime-score fields in fixture response; none were recognised for the selected Bayern fixture.
- **Three:** pre-match home/draw/away 1X2 prices. Code tries `historical_match_odds` in Supabase, prioritising Bet365, Betfair Exchange, William Hill, Pinnacle, using stored `last_seen` pre-match prices. The current-day matches are absent from `historical_xg`; the `ht_odds_trial_20261120` table had **zero rows** when queried, so tonight's stored prices could not be loaded.
- Supabase project reference: `blokxfllmygudeucnhhb`. NEVER expose, delete or change keys or stored historical data. `historical_match_odds` fields include `match_id`, `odds_payload`, `fetch_status`; nested JSON `data.bookmakers[*].markets.match_odds.{home,draw,away}.{opening,last_seen}`.
- Old page's `ht_odds_trial_20261120` expander showed `APIError`; error reporting was improved, but the table being empty is independently confirmed. Do not claim that this alone explains the APIError.

## Next work (priority order)
1. Inspect TheStatsAPI match/score response and documented halftime-score fields; map verified halftime goals without confusing live or final scores. If unavailable, require only the two manual score inputs.
2. Implement **bounded pre-kickoff odds collection** into an appropriate existing Supabase store, using genuine pre-match 1X2 quotes. Check available data and schema first; do not invent prices, call last-seen in-play odds "pre-match", or use undocumented API paths. Keep API usage controlled.
3. Once score and pre-match odds are verified, automatically price the selected fixture; then progress to **all halftime fixtures in one compact list** with fair odds and data-readiness indicators.
4. Only display model-versus-bookmaker edges if actual relevant **current and executable** market quotes exist. Stored pre-match odds are model strength inputs, NOT halftime market quotes.
5. Test with real fixtures and verify Streamlit rendering, data provenance, missing-value handling, and mobile layout. Keep old page as fallback until replacement is proven.

## Model and audit context
- Current deployed model: `model_artifacts/halftime_second_half_models.joblib`; original page uses its scaler/models and a probability-coherence layer.
- Research workflow: `.github/workflows/ht_calibration_audit.yml`, `scripts/retrain_ht_chronological_audit.py`; separate retrospective ~2,010-match logistic-regression evaluation. This is **not** a matched comparison proving the research model superior. Do not switch models without fair head-to-head evaluation.
- Previous research showed modest calibration differences and no demonstrated betting ROI. Do not overclaim an edge.

## Useful source files
- `pages/94_Quick_Halftime_Scanner.py`
- `pages/95_Half_Time_Fair_Odds.py`
- `lightweight_fixture_feed.py` — fixture API, 60-second caching, labels.
- `statsapi_refresh.py` — selected league IDs and bounded historical stats fetching.
- `halftime_snapshot_pricing.py` — descriptive historical snapshot analysis.
- `model_artifacts/halftime_second_half_models.joblib`
- `research_results/ht_large_chronological_comparison.csv`

## User workflow preferences
Use short, direct updates; perform requested GitHub work rather than only outlining it. Provide clickable **Streamlit app links** when verified, not GitHub source links presented as the dashboard. Keep pages phone-friendly, avoid side-scrolling, manual inputs, endless calibration and unverified profitability claims. Preserve all keys and historical data.


---

# Handover update — Independent Claude review (20 November 2026)

## Status at pause
The existing scanner code remains committed; **no fixes from the independent review have yet been implemented or verified**. Do not describe the following as independently verified by ChatGPT: Claude reported that he inspected repository code, committed outputs and handover, but did not execute the app or query Supabase. The user wants the project resumed with a focus on reliability rather than endless model tuning.

## Claude's reported findings (second opinion, pending independent verification)
1. **Odds collector may be broken:** `collect_four_prematch_odds_20261120.py` reportedly contains literal `\\n` characters causing a Python `SyntaxError`. Its GitHub workflow reportedly runs `py_compile` first, which would prevent collection. Check actual source and workflow, reproduce compile error, then fix and test. This could explain the empty `ht_odds_trial_20261120` table, but is not yet independently confirmed.
2. **Fixture phase classification:** `phase()` in `pages/94_Quick_Halftime_Scanner.py` reportedly uses substring matching, so `ft` within `halftime` could misclassify HT as finished. Reuse the existing `fixture_status()` in `fixture_live_status.py` after confirming its semantics.
3. **Half-time score:** scanner reportedly omits `halfTime` field that `collect_new_completed_fixtures.py` recognises. Inspect actual API payloads and cross-check HT goal timeline (including own-goal attribution); never infer HT score from final score.
4. **Model loading and dependency:** scanner reportedly downloads and unpickles `model_artifacts/halftime_second_half_models.joblib` from raw GitHub main at runtime although the artifact is in repo. Prefer local loading with a controlled artifact and compatible, pinned scikit-learn version; verify the actual deployment requirements before changes.
5. **Train/serve feature skew:** historical training uses timeline-derived shots/corners/red cards while scanner uses `stats.overview.first_half`. Compare both on ~200 finished matches; inspect red-card double counting and bookmaker odds source/timing before trusting live probabilities.
6. **Efficiency/security:** fixture feed may fetch up to 20 pages per cache miss before league filtering; `SUPABASE_SECRET_KEY` bypasses RLS, so assess whether public app exposes any unsafe database operations. Preserve secrets; never print credentials.
7. **Model evidence:** Claude reports walk-forward `period < month` and train-only scaler fitting; committed CSVs may not match current scripts (369-match recent holdout vs 2,000-match code). Claimed skill versus constant forecasts: next goal +0.044 log loss, 2H result +0.061, home/away scores ~+0.03, over-goal markets +0.005–0.007, both-score ~0. No independently established bookmaker-beating edge. These are **Claude's calculations**, not reproduced in this handover.
8. **Model replacement:** research and deployed models reportedly use same C=1 logistic architecture and 18 features; no fair matched head-to-head. Freeze model v1 pending paired out-of-sample comparison and uncertainty estimates. Claude's +0.002 improvement threshold is a heuristic, not universal.
9. **Repo clutter:** ~100 workflows, eight `test_app*` copies, dated one-off scripts and a ~24 MB committed predictions CSV; archive only after identifying dependencies, and avoid deleting useful data.

## Agreed priorities for next chat
**P1 — Fix pre-match odds collection.** Inspect/compile the reported broken collector and its workflow. Repair, add bounded idempotent pre-kickoff snapshots (for example around 10 minutes before kickoff) with bookmaker, observed_at and match_id. Check API endpoint and data provenance. GitHub Actions cron is best-effort; no guarantee of exact timing. Don't backfill live prices as pre-match.

**P2 — Confirm HT score and feature parity.** Inspect one raw API match/stats/timeline payload, use explicitly labelled HT scores or verified goal events, and compare training-vs-live feature definitions across ~200 completed matches. Ensure red cards and own goals aren't double counted.

**P3 — Genuine multi-match mobile scanner.** Replace per-match form-first flow with compact read-only list from stored snapshots: fixture, HT score, readiness, 3–4 fair odds, red-card warning, data freshness; expand for full markets; refresh with bounded calls/caching. Use existing local model, pin runtime dependency versions and fix status classification. Keep original dashboard as fallback.

**P4 — Real HT market quote logging and paper testing.** Check TheStatsAPI's actual live odds coverage; capture timestamped back/lay prices and available sizes where provided. Never call model probability a proven betting edge; use executable prices, costs, commission and out-of-sample tests.

**P5 — Freeze model and tidy audit trail.** Avoid further calibration/model arms until data collection works. Reconcile committed evaluation files with generating script, add paired confidence intervals; investigate both-score's weak skill before hiding it. Archive clutter cautiously.

## Resume instructions
"Continue **New Scanner** in `pngayton-droid/Star-lizard-test`. Read `NEW_SCANNER.md` and inspect `collect_four_prematch_odds_20261120.py`, its GitHub Actions workflow, `pages/94_Quick_Halftime_Scanner.py`, `fixture_live_status.py`, the HT model/training code and data helpers. First reproduce and fix the reported odds collector SyntaxError, with a syntax check and a safe test. Then resolve verified HT score and training/live feature parity before building the automatic multi-match view. Do not change/delete existing keys, model, historical data or old dashboard. Clearly distinguish Claude's findings from defects you personally verified."

## Important communication notes
The user works on mobile and prefers the assistant to carry out GitHub/Supabase work directly, provide concise progress and copyable commands, and avoid asking to manually copy lots of code. The user requested this handover to allow a new chat to continue without re-explaining the project.


---

## 21 November 2026 — First dashboard repair commits

Actual repository files were inspected and these **source changes were committed**:
- `scripts/collect_four_prematch_odds_20261120.py`: repaired the literal escaped newline sequence in the `norm` definition. Commit `4c768de5fd601466bb00ebafd4bc67b973bb9d06`. **Important:** this is a dated four-match trial hard-coded to `DAY="2026-11-20"`; repairing its syntax does **not** make it a functioning recurring collector on 21 November. Its runtime/API/database behaviour still needs testing, and it must be redesigned before using for future fixtures.
- `pages/94_Quick_Halftime_Scanner.py`: replaced substring status checks with existing `fixture_live_status.fixture_status`, changed model loading from remote GitHub download to the committed local joblib file, and added `score.halfTime` / `fixture.halfTime` to explicit HT-score lookup. Commit `345d1583572a1644c792b0386c1fb155e0bac219`.
- These are GitHub commits, **not verified live Streamlit deployment or successful data collection**. Validate syntax, imports, deployed app and API payloads next.
- The larger outstanding tasks remain: recurring bounded pre-kickoff odds snapshots, HT score payload verification, training-vs-live feature parity, and true automatic multi-match mobile scanner. Existing model, old dashboard, keys and historical data were not intentionally modified.


## 21 November 2026 — Recurring odds collector created
- Added `scripts/collect_new_scanner_prematch_odds.py` (commit `7095a0e5abd0be18469a1b1261b112fa6374f49b`): bounded API collection of selected-league matches kicking off within 20 minutes, preserving bookmaker, observed_at and complete odds market payloads in existing `ht_odds_trial_20261120` table under `snapshot_kind=prematch_within_20m`. The table name is legacy; no schema or historical data was deleted.
- Added `.github/workflows/new_scanner_prematch_odds.yml` (commit `7d41d1667cf46a18a6ecfa64fab684180fc1f4ff`): cron every ten minutes between 08:00 and 22:59 UTC plus manual dispatch; workflow checks Python syntax before running, uses existing repository secrets. GitHub Actions scheduling is best-effort, so the precise pre-kickoff window is not guaranteed.
- Updated `pages/94_Quick_Halftime_Scanner.py` (commit `fed43a4f450abfdfd22b18cbea238dad8200edd6`) to prefer new timestamped odds snapshots, then historical odds.
- **Still unverified:** first successful scheduled/manual Actions run, actual TheStatsAPI odds response, bookmaker availability, successful Supabase insert, and end-to-end Streamlit prices. No claim that odds have actually been collected.
- **Next:** check GitHub Actions run logs and Supabase snapshot rows; fix any issues; confirm HT score payload; compare live-vs-training features; then implement genuine multi-match list. Consider improving pagination (3 pages max), scheduling coverage and idempotence before relying on production collection.


## 21 November 2026 — Scanner promoted to main page
- `pro_starlizard.py` now immediately opens `pages/94_Quick_Halftime_Scanner.py` via `st.switch_page`. Commit `bc4f5a76bb3fd84c9f0709608a240dc4224cedf4`.
- The previous complete `pro_starlizard.py` was preserved at `pages/96_Legacy_Match_Analysis.py` (commit `e2e738cd775b4f7d4c2780ccf65173aba007c8f9`). No data/model deletion.
- Scanner now retains the original PRO STARLIZARD dark-blue styling and header artwork; collapsed links to the legacy match analysis and old halftime calculator. Commit `a1a0031a44d7d2ee50957864c7e763ecfa3a1c4e`.
- Earlier today, independent odds lookup error handling and a diagnostic expander were committed, and the manual odds inputs were collapsed. User screenshot confirmed scanner v8 deployed before the home-page promotion.
- **Deployment of new home-page redirect and retained artwork is not yet verified.** Validate root URL `https://pro-starlizard-preview.streamlit.app/` after deployment, ensure legacy page imports work, and continue solving odds APIError and automatic multi-fixture pricing.


---

## 21 November 2026 — MATCH MATRIX handover after successful fixture-cache run

### Current state and evidence (05:45 UK time, 21 November)
- User confirmed a manual GitHub Actions run of `.github/workflows/new_scanner_prematch_odds.yml` succeeded in 16 seconds. The **Capture upcoming fixture odds** log explicitly reported:
  ```
  Using cached daily kickoff schedule: 413 fixtures
  Eligible fixtures: 0 API calls: 0
  FINISHED saved 0 calls 0
  ```
- This **confirms today's full API fixture schedule was cached and restored** (413 across all API leagues, not 413 selected fixtures). The scanner previously displayed **52 fixtures in selected leagues**; this 52 was not independently reconciled against the cached list. At 05:45 there were no fixtures within the 25-minute collection window, so **no bookmaker odds were captured** and no API requests were consumed by that run.
- The *first* manual run (around 05:39) displayed a green tick but the log said `Fixture feed exceeded 3 pages; stop without caching`; it had silently returned without collecting anything. Fixed pagination to use API `meta.total_pages`, up to 20 pages, and to raise on incomplete data: commit `a8c7c3670e5f90ba5f4844e525ce8a45e854bdcb`. **Important: the 05:45 run restored a cached 413-fixture schedule; it does not itself prove that the newly corrected pagination executed on a cache miss.** The restored cache's existence is evidence of a previous successful schedule save.
- Supabase `ht_odds_trial_20261120` was directly queried before the first kickoff and had **zero `prematch_within_20m` snapshots**. This is expected at that hour. No successful odds insert or dashboard prefill has yet been observed.

### Current source and workflow
- Main dashboard: `pro_starlizard.py` redirects to `pages/94_Quick_Halftime_Scanner.py`.
- **Do not change the user's approved design**: THE MATCH MATRIX in red-and-gold Manchester United colours, large Manchester United crest, mobile-safe top padding `.block-container{padding-top:5rem!important}` to avoid the Streamlit toolbar overlap. The previous blue PRO STARLIZARD interface is archived at `pages/96_Legacy_Match_Analysis.py`; original halftime calculator at `pages/95_Half_Time_Fair_Odds.py`.
- Odds collector: `scripts/collect_new_scanner_prematch_odds.py`. Workflow: `.github/workflows/new_scanner_prematch_odds.yml`, scheduled every **5 minutes from 08:00 through 22:59 UTC**, plus manual dispatch. Daily schedule cached via `actions/cache@v4` using date/run_id key and date restore prefix. Selected league IDs hardcoded in collector; verify they match `statsapi_refresh.LEAGUES`.
- Collector requests `GET /api/football/matches/{id}/odds?bookmaker=bet365,betfair-exchange,pinnacle` only if kickoff is within **25 minutes in the future**. Up to **35 API calls per invocation**, with a hardcoded **500-request reserve** (user reported 6,475 requests remaining at 05:30). It ignores stale fixture `odds_available` flags. Stores complete 1X2 `last_seen` price payloads with `observed_at`, `bookmaker`, `match_id` and `snapshot_kind=prematch_within_20m` (legacy label; actual window is now 25 minutes) in `ht_odds_trial_20261120`.
- Collector fixes committed: `247e10a4147c5c57986662452f4343d8ce096561` (odds_available filter removed, 35-call cap, 25-minute window, improved logs), `ac2646e2580d387e9fea9493974b51db7184862a` (five-minute workflow and run-id cache), `a8c7c3670e5f90ba5f4844e525ce8a45e854bdcb` (correct fixture pagination and visible failure).
- Supabase table columns confirmed: `id bigint`, `match_id text`, `fixture text`, `competition_id text`, `observed_at timestamptz`, `match_status text`, `elapsed_minutes integer`, `bookmaker text`, `markets jsonb`, `snapshot_kind text`. Unique index on `(match_id, observed_at, bookmaker)`, **not** `(match_id, bookmaker, snapshot_kind)`. Existing row check and workflow concurrency mitigate duplicates but are not atomic; plain `.insert()` remains. No schema changed.
- The scanner's `stored_prematch(mid)` queries new snapshot table first, then `historical_match_odds`; it prioritises Bet365, Betfair Exchange, William Hill, Pinnacle. William Hill is not a supported TheStatsAPI bookmaker slug according to Claude's doc review; current collector does not request it. When saved prices exist and input boxes are empty, the home/draw/away pre-match odds fields are prefilled. Database lookup cached for 300 seconds; existing non-empty widget values are not overwritten.
- The scanner now **automatically fetches first-half stats once per selected match only when the fixture's explicit status is `ht`, `half_time` or `halftime`**, while preserving the manual button. Commit `422ec4e1a8e7934d65f2e82d43b79a6768820269`. **This automatic HT behaviour is committed but NOT yet tested in a live halftime fixture.** It does not guarantee verified HT score or all fields; no fabricated values are allowed.
- **Halftime bookmaker odds are NOT automatically collected yet.** The pre-match 1X2 prices are model inputs and must never be represented as halftime market quotes. Current model needs verified HT score, first-half stats, and pre-match 1X2 odds to price 2H markets. The model file `model_artifacts/halftime_second_half_models.joblib` and historical data were preserved.

### Immediate next checkpoints (Saturday 21 November)
1. **First kickoff:** Manchester City v Fulham, **12:30 GMT**. Odds collector should start checking this fixture within the 25-minute window (~12:05). GitHub Actions cron is best-effort; verify a run actually fires before kickoff.
2. Inspect GitHub Actions log for eligible fixture IDs, bookmaker names and `Saved:` messages. Verify corresponding rows in Supabase with `observed_at` strictly before kickoff, and complete 1X2 prices. Confirm scanner auto-populates home/draw/away pre-match odds. Do not claim success based only on a green workflow tick.
3. At verified halftime (~13:15, approximate), select the match and check automatic stats, explicit halftime goals, model inputs and resulting fair odds. Never substitute current score for HT score.
4. Research the actual TheStatsAPI **halftime/in-play bookmaker odds coverage and response structure** before implementing timestamped HT odds collection. Use only documented supported endpoints, preserve API budget and distinguish quotes from model fair odds.
5. Future target: a genuinely automatic multi-fixture mobile halftime scanner with complete verified facts, genuine market comparison and a readiness indicator. No more unbounded calibration/model changes.

### Risks and guardrails
- The 413 cached matches are **all leagues**; validate filtering to the 10 intended league IDs. The saved cache is a snapshot; rescheduled fixtures may require refresh. Workflow only runs 08:00–22:59 UTC and may be delayed.
- `last_seen` is the latest API-recorded bookmaker price, not a timestamped exchange quote. `observed_at` proves only when *our request* occurred. Do not claim it is guaranteed closing price or executable.
- If odds endpoint returns 404/409/429, current collector skips; it does not retry within the same run. Its `RESERVE=500` does not preserve the user's currently reported 6,475 calls; consider stronger budget guard if needed. No live API or end-to-end odds insert verified yet.
- In the new conversation, read **this file and the actual current GitHub code first**. Keep original keys, Supabase historical tables, model, old pages and Manchester United branding. User prefers direct GitHub edits and concise reports, not pasted code or repeated manual steps.


## 22 Nov 2026 — rapid halftime collection trial
- Existing prematch odds workflow remains intact; its old single-shot halftime step was removed to avoid races.
- New workflow: `.github/workflows/match_matrix_rapid_halftime.yml`, scheduled at UTC minutes 02/17/32/47, 08:00–22:59. Separate concurrency group; 16-minute job timeout; 13-minute polling loop.
- New script: `scripts/poll_match_matrix_halftime.py`, 45-second polling, live fixture list status detection, /football/matches/{id}/live-stats two snapshots at least 35 seconds apart, required xG/shots/SOT/corners, exact kickoff/capture/first_seen timestamps, quota cap 45 requests per run and reserve 500, HTTP 429 stop. Uses shared daily fixture cache from prematch collector. Skips if no relevant kickoff windows.
- Supabase `match_matrix_halftime_stats` extended with `ht_first_seen_at`, `quality`, `api_updated_at`, `elapsed_minutes`, `raw_meta`, `second_observed_at`.
- Previous 21 Nov three captures validated against finalised `historical_match_events.stats_data`: Dundee and Feyenoord xG exactly matched; Real Madrid xG varied by 0.01 per team; all corners matched.
- Important: the new rapid poller has NOT yet been proven in a live run; check Actions logs and compare actual observed_at minus kickoff_utc today. GitHub schedule remains best-effort. API halftime status freshness also remains unverified.
