"""Historical walk-forward halftime fair odds. No fabricated live predictions."""
import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Half-Time Fair Odds", layout="wide")
st.title("Half-Time Fair Odds")
st.caption("Verified historical walk-forward predictions from TheStatsAPI. Not live fixture prices.")
BASE = "https://raw.githubusercontent.com/pngayton-droid/Star-lizard-test/main/research_results/"
@st.cache_data(ttl=1800, show_spinner="Loading archived predictions…")
def load_csv(name):
    return pd.read_csv(BASE + name)

try:
    summary = load_csv("ht_second_half_fair_odds_summary.csv")
    predictions = load_csv("ht_second_half_fair_odds_predictions.csv")
except Exception as exc:
    st.error(f"Unable to load research outputs: {exc}")
    st.stop()

st.subheader("Historical model evaluation")
st.dataframe(summary.sort_values(["split", "market"]), hide_index=True, use_container_width=True)
st.divider()
st.subheader("Inspect actual historical fair prices")
st.info("These prices were generated walk-forward for historical matches. A live halftime pricing model has not yet been deployed.")
split = st.selectbox("Test period", ["holdout", "development"])
subset = predictions.loc[predictions["split"].eq(split)].copy()
subset["fixture"] = subset["match_date"].astype(str) + " | " + subset["home_team"].astype(str) + " v " + subset["away_team"].astype(str) + " (HT " + subset["ht_score"].astype(str) + ")"
fixtures = subset[["match_id", "fixture"]].drop_duplicates().sort_values("fixture", ascending=False)
if fixtures.empty:
    st.warning("No historical predictions for this period.")
    st.stop()
options = dict(zip(fixtures["fixture"], fixtures["match_id"]))
chosen = st.selectbox("Historical fixture", list(options))
selected = subset.loc[subset["match_id"].eq(options[chosen]), ["market", "selection", "probability", "fair_odds", "won"]].copy()
selected["probability"] = (selected["probability"] * 100).round(2)
selected["fair_odds"] = selected["fair_odds"].round(3)
selected = selected.rename(columns={"probability": "Probability (%)", "fair_odds": "Fair decimal odds", "won": "Occurred (1=yes)"})
st.dataframe(selected.sort_values(["market", "selection"]), hide_index=True, use_container_width=True)
st.caption("Fair decimal odds = 1 / model probability. No bookmaker odds or ROI assumed.")
