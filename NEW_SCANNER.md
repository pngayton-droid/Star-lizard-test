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
