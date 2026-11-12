"""Half-time outcome research from stored match outcomes, no paid API calls.

Descriptive second-half scoring rates are NOT next-goal probabilities.
"""
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="PRO STARLIZARD | Half-time Research", page_icon="⏱️", layout="wide")
st.title("⏱️ Half-time & second-half research")
st.caption("Stored historical matches only. No TheStatsAPI requests.")
st.warning("This page measures observed second-half outcomes, NOT betting profit. "
           "A trailing team scoring in the second half is not the same as scoring the next goal. "
           "Historical in-play odds are required before assessing betting value.")

@st.cache_data(ttl=3600, show_spinner="Loading historical half-time research...")
def load_data():
    db = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])
    rows = []
    for start in range(0, 20000, 1000):
        batch = (db.table("halftime_research_outcomes")
                 .select("competition_id,match_date,home_team,away_team,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_second_half_goals,away_second_half_goals,trailing_side,trailing_ht_xg")
                 .order("match_date").range(start, start+999).execute()).data or []
        rows.extend(batch)
        if len(batch) < 1000:
            break
    return pd.DataFrame(rows)

try:
    df = load_data()
    if df.empty:
        st.warning("No stored historical matches found.")
        st.stop()
    numeric = ["home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg",
               "home_second_half_goals","away_second_half_goals","trailing_ht_xg"]
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    st.metric("Historical fixtures loaded", f"{len(df):,}")
    leagues = sorted(df["competition_id"].dropna().unique().tolist())
    league = st.selectbox("Competition", ["All"] + leagues)
    if league != "All":
        df = df[df["competition_id"] == league].copy()
    threshold = st.slider("Trailing team's minimum half-time xG", 0.0, 1.5, 0.2, 0.05)
    side = st.selectbox("Trailing team", ["Both", "Home", "Away"])
    deficit = st.selectbox("Half-time deficit", ["Any", "1 goal", "2 goals", "3+ goals"])
    df = df[df["trailing_side"].notna() & df["trailing_ht_xg"].ge(threshold)].copy()
    df["Deficit"] = (df["home_ht_goals"] - df["away_ht_goals"]).abs()
    df["Trailing 2H goals"] = df.apply(
        lambda r: r["home_second_half_goals"] if str(r["trailing_side"]).lower() == "home"
        else r["away_second_half_goals"], axis=1)
    df["Leading 2H goals"] = df.apply(
        lambda r: r["away_second_half_goals"] if str(r["trailing_side"]).lower() == "home"
        else r["home_second_half_goals"], axis=1)
    if side != "Both":
        df = df[df["trailing_side"].str.lower() == side.lower()]
    if deficit != "Any":
        df = df[df["Deficit"].ge(3) if deficit == "3+ goals" else df["Deficit"].eq(int(deficit[0]))]
    df = df.dropna(subset=["Trailing 2H goals", "Leading 2H goals"])
    st.metric("Qualifying fixtures", f"{len(df):,}")
    if df.empty:
        st.info("No matches qualify.")
        st.stop()
    scored = df["Trailing 2H goals"].ge(1)
    st.metric("Trailing team scored in second half", f"{scored.mean():.1%}")
    st.metric("Trailing team scored 2+ second-half goals", f"{df['Trailing 2H goals'].ge(2).mean():.1%}")
    st.metric("No second-half goals", f"{(df['Trailing 2H goals'].eq(0) & df['Leading 2H goals'].eq(0)).mean():.1%}")
    st.caption("Scoring in the second half does not establish who scored FIRST after half-time.")
    st.subheader("Second-half goal distribution")
    totals = df["Trailing 2H goals"] + df["Leading 2H goals"]
    distribution = pd.DataFrame({
        "Second-half goals": ["0", "1", "2", "3+"],
        "Matches": [int(totals.eq(0).sum()), int(totals.eq(1).sum()),
                    int(totals.eq(2).sum()), int(totals.ge(3).sum())]})
    distribution["Share"] = distribution["Matches"] / len(df)
    st.dataframe(distribution, hide_index=True, use_container_width=True)
    st.subheader("Trailing team's scoring by deficit and venue")
    df["Trailing venue"] = df["trailing_side"].str.capitalize()
    df["Deficit band"] = df["Deficit"].clip(upper=3).map({1:"1",2:"2",3:"3+"})
    summary = (df.assign(Scored=scored.astype(int))
               .groupby(["Trailing venue","Deficit band"], observed=True)
               .agg(Matches=("Scored","size"), Scored=("Scored","sum"),
                    Mean_HT_xG=("trailing_ht_xg","mean")).reset_index())
    summary["Scoring rate"] = summary["Scored"] / summary["Matches"]
    st.dataframe(summary, hide_index=True, use_container_width=True)
    st.subheader("Chronological holdout check")
    df = df.sort_values("match_date")
    cutoff = int(len(df)*.7)
    for label, part in (("Earlier 70%", df.iloc[:cutoff]), ("Later 30%", df.iloc[cutoff:])):
        if len(part):
            st.write(f"{label}: {len(part):,} matches; trailing side scored in 2H: {part['Trailing 2H goals'].ge(1).mean():.1%}")
    st.caption("These are descriptive frequency comparisons, not a trained prediction model. "
               "No pre-match favourite filter is applied until odds are joined reliably by fixture ID.")
    st.download_button("Download qualifying half-time outcomes CSV",
                       df.to_csv(index=False).encode("utf-8"),
                       file_name="starlizard_halftime_outcomes.csv", mime="text/csv")
except Exception as exc:
    st.error(f"Could not load half-time research: {type(exc).__name__}: {exc}")
