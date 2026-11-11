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
st.caption("This screen does not yet calculate next-goal outcomes. Those require event-level sequence queries and HT stoppage-time reconciliation.")
st.dataframe(qual[["match_date","league","home_team","away_team","ht_home","ht_away","ht_xg_home","ht_xg_away","b365_home","b365_away","trailing_side"]], use_container_width=True, hide_index=True)
st.download_button("Download filtered matches (CSV)", qual.to_csv(index=False).encode("utf-8"), "starlizard_historical_screen.csv", "text/csv")
