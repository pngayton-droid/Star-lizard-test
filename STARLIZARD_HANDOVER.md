# PRO STARLIZARD — PROJECT HANDOVER / COVER NOTE
**Updated:** 19 November 2026  
**Repository:** `pngayton-droid/Star-lizard-test` (`main`)  
**Main dashboard:** `pages/Similarity_Pricing.py`  
**Preview:** https://pro-starlizard-preview.streamlit.app/Similarity_Pricing

## Read this first in a new chat
The owner is developing a historical **Match Matrix** that finds comparable prior football fixtures and prices 1X2, goals, corners and cards using TheStatsAPI data. **Current priority is fixing 1X2 probability accuracy**, particularly severe overvaluation of long-priced underdogs. Trading ideas are **parked**. Do not assume historical positive results demonstrate a real edge. Do not delete or replace historical data, API credentials, or existing production dashboard without explicit permission.

**Next action:** Check whether the workflow **“Test Matrix league and opponent-strength similarity”** has finished, inspect its CSV outputs, explain findings in concise phone-friendly language, and decide whether a genuinely improved similarity method warrants further *out-of-sample* testing. Do not automatically deploy the winning variant.

Workflow: https://github.com/pngayton-droid/Star-lizard-test/actions/workflows/audit_match_odds_similarity_quality.yml  
Script: `scripts/audit_match_odds_similarity_quality.py`  
Expected outputs:
- `research_results/match_odds_similarity_quality_summary.csv`
- `research_results/match_odds_similarity_quality_forecasts.csv`

At time of writing the summary file **was not yet present**. This test compares: (1) original combined 250 nearest analogues, (2) same-league 250, (3) extra emphasis on relative pre-match PPG and goal-difference gap, and (4) same-league plus strength-gap. All neighbour fixtures must predate the target fixture. Outputs are 2025 and 2026 Brier/log loss, Bet365 no-vig Brier, and Bet365 last-seen 1X2 selection ROI. **Important:** the variants are being compared on potentially different eligible fixture sets (same-league minimum 50), so compare common-fixture subsets before declaring a winner. Variant tuning on 2025–2026 makes those years no longer untouched for subsequent claims.

## What the current Matrix actually does
`features()` constructs strictly pre-match features from historical fixtures, including last-five home/away venue form, PPG, goal difference per match, league rank, xG where available, shots on target, corners and cards. `analogues()` scores prior fixtures by feature distance, allowing other competitions with a small penalty; it returns eligible matches within distance 2.0, sorted by closeness. Current dashboard **uses strength-only 250 for match odds**, and **combined 250 for other markets**. The combined approach includes recent-form and several market-specific features. The model converts frequencies among historical analogues into fair odds. Betting audits often choose the **single 1X2 outcome with maximum predicted EV**, if EV >= 5%, and compare with saved Bet365 odds. This selection process can magnify estimation error and prefer implausibly high-priced underdogs.

## Verified historical research (do not mix samples)
1. **Full strength-only 1X2 audit:** 12,203 Bet365 last-seen selections, **−12.77% ROI** (−1,559.438 units). 2021–2026 yearly results all negative. `research_results/match_odds_matrix_full_summary.csv` and `match_odds_matrix_full_bets.csv`.
2. **Paired Matrix comparison**, same 14,886 fixtures for accuracy: league-average baseline Brier **0.216734**; combined 250 **0.200940**; strength 250 **0.200954**; strength all **0.208198**; combined all **0.214891**. Bet365 betting subsets: combined 250 **11,742 bets, −11.87% ROI**; strength 250 **11,634 bets, −12.48%**; combined all **−13.53%**; strength all **−14.38%**. This baseline is a *league-average* baseline, **not the bookmaker**. `research_results/match_odds_paired_accuracy_summary.csv`, `match_odds_paired_roi_summary.csv`.
3. **Strength-only 1X2 odds bands**, Bet365 last-seen: 1.20–1.49: 43 bets +17.54% (tiny); 1.50–1.99: 467 −1.20%; 2.00–2.99: 2,401 −9.66%; 3.00–3.99: 3,211 −13.02%; 4.00–5.99: 3,320 −8.69%; **6.00–20.00: 2,761 −22.56%**, despite predicted **+74.44%**. `research_results/match_odds_band_roi.csv`, `match_odds_band_year.csv`.
4. **Independent calibration test:** combined 250 predictions on 9,917 matches from 2021–2024 used to fit multinomial logistic calibration **without bookmaker input**; 2025–2026 validation covered 5,194 fixtures. Brier: original **0.204303**, calibrated **0.204007**, Bet365 no-vig **0.198617** (lower is better). Original 3,873 selected bets **−9.86% ROI**, calibrated 3,672 **−8.48%**. Calibration improved modestly but did **not** fix exaggerated value. `research_results/match_odds_calibration_summary.csv`; script `scripts/audit_match_odds_calibration.py`.
5. **Value-selection diagnostic:** on 2025–2026 combined, calibrated Matrix 5% EV threshold: 3,672 bets **−8.48%**; 15%: 2,329 **−9.69%**; 30%: 1,163 **−3.08%**. Capping odds below 3.00 at 5% EV: calibrated 1,144 bets **−3.05%**. Mixing calibrated probabilities with 75% bookmaker no-vig implied probabilities yielded 842 bets **−1.78%** at 5% EV. A 50% bookmaker blend with 30% EV showed **249 bets +3.29%** across 2025–2026 (+2.25% in 2025, +5.55% in 2026), **but this was discovered by trying multiple variants on the same years, so is not independently validated or a demonstrated edge**. `research_results/match_odds_value_selection_diagnostic.csv`; script `scripts/audit_match_odds_value_selection.py`.
6. **Other markets:** Asian goals unders 5,282 bets **−6.83%**; Asian corners 4,762 **−4.64%**; Asian cards including red-card proxy 5,832 **−5.10%**. Ordinary corners and cards also negative. These were removed from live Asian panels after audit. Do not reintroduce on apparent in-sample gains.

## What we're trying to learn
The user's question: *“How is it that we're picking games that have played out before in similar circumstances but getting it wrong? Is it because the model is purely looking for value and will take it whenever?”* Yes, the audit's highest-EV selection mechanism can chase spurious value, but similarity quality and calibration are also suspect. In particular, comparing teams with similar five-match numbers may not control for opponent strength, league strength, promotions, sample size, or underlying team quality. The **bookmaker's no-vig probabilities currently beat Matrix accuracy**, so an apparent Matrix edge is not credible without much stronger evidence.

## Guardrails and next research
- Use **TheStatsAPI** as source of historical matches and stored Bet365 odds; no Understat mixing. Historical data is stored in Supabase; do not erase anything or expose secret keys.
- Keep historical features strictly *as of kickoff*, avoid same-day leakage, and keep a truly later test set for any tuned model.
- For the running similarity test, inspect **actual output CSVs**, check whether the workflow succeeded, and verify matching sample sizes before comparisons. If improvement is small or unstable, say so.
- If results justify it, run a **paired common-fixture** head-to-head and preferably a fresh time-based holdout or future paper test. Check overall Brier and log loss against Bet365 no-vig; measure calibration by price band, not just ROI.
- Keep the existing Streamlit Matrix unchanged until improvement is convincing. User wants minimal interface churn and concise actual results rather than lengthy iterative calibration cycles.
- Don't imply a betting system is profitable on retrospective, cherry-picked samples. Opening odds coverage is sparse; most audits use **last-seen Bet365 odds**.
- **Trading strategy is on hold**. Older first-goal audit was only goal-sequence frequencies, not executable trading profitability (no real in-play Betfair lay prices).

## Important project paths
- `pages/Similarity_Pricing.py` — live Matrix calculations and interface.
- `scripts/audit_match_odds_matrix_full.py` — initial strength-only 1X2 audit.
- `scripts/audit_match_odds_paired.py` — combined/strength and 250/all comparison.
- `scripts/audit_match_odds_bands.py` — odds bands.
- `scripts/audit_match_odds_calibration.py` — fitted probability correction.
- `scripts/audit_match_odds_value_selection.py` — EV threshold, odds cap, bookmaker blend diagnostic.
- `scripts/audit_match_odds_similarity_quality.py` — **current test**.
- `.github/workflows/` — corresponding manually runnable GitHub Actions.
- `research_results/` — committed result CSVs.

## Practical handoff instruction
In a new chat, say: **“Read STARLIZARD_HANDOVER.md in my GitHub Star-lizard-test repository, check the latest similarity-quality workflow and results, and continue improving the main 1X2 Matrix. Do not change the dashboard yet.”**

This note is a research handover, not proof of any betting edge.
