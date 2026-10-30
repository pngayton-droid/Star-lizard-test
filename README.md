# Saturday football pricing lab — isolated prototype

This is a standalone Streamlit app, separate from the production scanner. No live API calls are made. No API key is required. Historical match results after the selected as-of date are excluded from team ratings. Odds are entered manually. The in-play section is an illustrative time-scaled Poisson calculation, **not** a validated live model.

## Run locally

1. Put `football_merged_32653.csv` from the existing repository beside `test_app.py` (not included in this ZIP to avoid duplication).
2. `pip install -r requirements.txt`
3. `streamlit run test_app.py`

## Deploy without modifying the existing scanner

Create a separate Streamlit Community Cloud app pointing to `test_app.py` on a test branch/repository, with the CSV and the other files in the same directory. Do not change the existing app's entrypoint. If using the same repository, add the files through a new branch first.

## Known limitations

* The original model's goal-based ratings are weaker than no-vig bookmaker 1X2 odds on historical tests. No profitable edge demonstrated.
* Team names, promotions, match dates and goal distribution assumptions need more validation.
* Correct-score prices are mathematical outputs, not observed bookmaker odds.
* The in-play calculation is a sandbox and should not be used as a trading signal.
* API coverage, price freshness and latency remain untested.
