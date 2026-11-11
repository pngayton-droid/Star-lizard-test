"""Private historical research, read-only. Requires SUPABASE_URL and SUPABASE_SECRET_KEY in Streamlit secrets."""
import os
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Historical Archive Research", layout="wide")
st.title("🦎 Historical Archive Research")
st.caption("Private, historical research only. This page does not place bets or modify records.")

def secret(name):
    try:
        return st.secrets.get(name) or os.environ.get(name)
    except Exception:
        return os.environ.get(name)

url, key = secret("SUPABASE_URL"), secret("SUPABASE_SECRET_KEY")
if not url or not key:
    st.error("Add SUPABASE_URL and SUPABASE_SECRET_KEY to Streamlit secrets to use this page.")
    st.stop()

@st.cache_data(ttl=900, show_spinner="Loading verified historical matches…")
def load():
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    all_rows = []
    page_size = 1000
    for offset in range(0, 10000, page_size):
        r = requests.get(url.rstrip("/") + "/rest/v1/archive_verified_match_research",
            params={"select": "*", "order": "match_date.asc", "limit": page_size, "offset": offset},
            headers=headers, timeout=45)
        r.raise_for_status()
        batch = r.json()
        all_rows.extend(batch)
        if len(batch) < page_size:
            break
    return pd.DataFrame(all_rows)

try:
    df = load()
except Exception as exc:
    st.error("Could not load private historical view. Check Streamlit secrets and service-role permissions.")
    st.code(str(exc))
    st.stop()
if df.empty:
    st.warning("No verified linked historical records available.")
    st.stop()

st.metric("Linked historical matches", f"{len(df):,}")
df["match_date"] = pd.to_datetime(df["match_date"], errors="coerce")
leagues = sorted(df["league"].dropna().unique().tolist())
chosen = st.multiselect("Leagues", leagues, default=leagues)
df = df[df["league"].isin(chosen)].copy()
st.subheader("Data coverage")
c1,c2,c3 = st.columns(3)
c1.metric("Verified goal sequences", f"{int(df['verified_goal_sequence'].fillna(False).sum()):,}")
c2.metric("Corners recorded", f"{int(df['has_corners'].fillna(False).sum()):,}")
c3.metric("Bet365 odds recorded", f"{int(df['has_b365_odds'].fillna(False).sum()):,}")

st.subheader("Half-time trailing-team next-goal screening")
st.caption("Exploratory filters only. The archive's HT xG uses a provisional minute ≤45 convention. Do not treat this as live-market ROI.")
min_xg = st.slider("Minimum trailing-team first-half xG", 0.0, 1.5, 0.2, 0.05)
min_price = st.slider("Minimum trailing team's pre-match win odds", 1.0, 5.0, 1.5, 0.05)
valid = df[df["verified_goal_sequence"].fillna(False) & df["has_ht_score"].fillna(False) & df["has_b365_odds"].fillna(False)].copy()
for field in ["ht_home","ht_away","ht_xg_home","ht_xg_away","b365_home","b365_away"]:
    valid[field] = pd.to_numeric(valid[field], errors="coerce")
home = (valid.ht_home < valid.ht_away) & (valid.ht_xg_home >= min_xg) & (valid.b365_home >= min_price)
away = (valid.ht_away < valid.ht_home) & (valid.ht_xg_away >= min_xg) & (valid.b365_away >= min_price)
qual = valid[home | away].copy()
qual["trailing_side"] = ["Home" if h else "Away" for h in home[home | away]]
st.metric("Qualifying historical matches", f"{len(qual):,}")
st.caption("Next-goal results use the first verified goal strictly after minute 45. Half-time stoppage-time convention remains provisional.")
@st.cache_data(ttl=900, show_spinner="Loading first second-half goals…")
def load_first_goals():
    headers = {"apikey": key, "Authorization": "Bearer " + key}
    rows = []
    for offset in range(0, 20000, 1000):
        r = requests.get(url.rstrip("/") + "/rest/v1/archive_first_second_half_goal",
            params={"select": "understat_id,first_goal_minute,first_goal_side", "order": "understat_id.asc", "limit": 1000, "offset": offset},
            headers=headers, timeout=45)
        r.raise_for_status()
        batch = r.json()
        rows.extend(batch)
        if len(batch) < 1000:
            break
    return pd.DataFrame(rows)

try:
    goals = load_first_goals()
    if goals.empty:
        goals = pd.DataFrame(columns=["understat_id","first_goal_minute","first_goal_side"])
    qual = qual.merge(goals, on="understat_id", how="left", validate="one_to_one")
    # The event data uses lowercase h/a; the display uses Home/Away.
    qual["trailing_code"] = qual["trailing_side"].map({"Home":"h","Away":"a"})
    qual["next_goal_hit"] = qual["first_goal_side"] == qual["trailing_code"]
    qual["next_goal_outcome"] = "Leader scored next"
    qual.loc[qual["first_goal_side"].isna(), "next_goal_outcome"] = "No recorded second-half goal"
    qual.loc[qual["next_goal_hit"], "next_goal_outcome"] = "Trailing team scored next"
    n = len(qual)
    hits = int(qual["next_goal_hit"].sum())
    no_goal = int(qual["first_goal_side"].isna().sum())
    m1,m2,m3 = st.columns(3)
    m1.metric("Trailing team scored next", f"{hits:,}")
    m2.metric("Strike rate", f"{hits/n:.1%}" if n else "—")
    m3.metric("No recorded second-half goal", f"{no_goal:,}")
    if n:
        st.subheader("Home versus away")
        summary = qual.groupby("trailing_side", dropna=False).agg(
            matches=("understat_id","size"), hits=("next_goal_hit","sum")).reset_index()
        summary["strike_rate"] = (summary["hits"] / summary["matches"] * 100).round(2)
        st.dataframe(summary, hide_index=True, use_container_width=True)
        st.subheader("Pre-match odds bands")
        qual["trailing_prematch_odds"] = qual["b365_home"].where(qual["trailing_side"]=="Home", qual["b365_away"])
        qual["odds_band"] = pd.cut(qual["trailing_prematch_odds"], bins=[0,1.5,2,3,4,5,10,float("inf")],
            labels=["<1.50","1.50–1.99","2.00–2.99","3.00–3.99","4.00–4.99","5.00–9.99","10+"])
        bands = qual.groupby("odds_band", observed=True).agg(matches=("understat_id","size"),
            hits=("next_goal_hit","sum")).reset_index()
        bands["strike_rate"] = (bands["hits"] / bands["matches"] * 100).round(2)
        st.dataframe(bands, hide_index=True, use_container_width=True)
except Exception as exc:
    st.warning("Next-goal outcomes could not be loaded; the screening table is still available.")
    st.code(str(exc))
st.dataframe(qual[["match_date","league","home_team","away_team","ht_home","ht_away","ht_xg_home","ht_xg_away","b365_home","b365_away","trailing_side"]], use_container_width=True, hide_index=True)
st.download_button("Download filtered matches (CSV)", qual.to_csv(index=False).encode("utf-8"), "starlizard_historical_screen.csv", "text/csv")
