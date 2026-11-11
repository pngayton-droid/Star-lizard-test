"""PRO STARLIZARD historical archive coverage and readiness dashboard."""
import streamlit as st
import pandas as pd
from archive_data_engine import load_coverage

st.set_page_config(page_title="Archive Data Coverage", layout="wide")
st.title("🦎 Archive Data Coverage")
st.caption("Read-only coverage of our imported historical archive. Calendar year, not football season.")
@st.cache_data(ttl=900)
def data():
    return load_coverage()
try:
    df=data()
except Exception as exc:
    st.error("Unable to load private archive coverage. Check Streamlit server secrets.")
    st.code(str(exc))
    st.stop()
if df.empty:
    st.warning("No archive coverage available.")
    st.stop()

metrics=["matches","ft_scores","ht_scores","corners","yellow_cards","b365_odds","verified_sequences","linked_matches"]
for col in metrics:
    df[col]=pd.to_numeric(df[col],errors="coerce").fillna(0).astype(int)
df["season_year"]=pd.to_numeric(df["season_year"],errors="coerce")
totals=df.groupby("source",as_index=False)[metrics].sum()
c1,c2,c3=st.columns(3)
for c,source in zip([c1,c2,c3],["Football-data","Understat","Cross-source linked"]):
    subset=totals[totals.source==source]
    c.metric(source, f"{int(subset.matches.iloc[0]):,}" if len(subset) else "0")

st.subheader("Explore coverage")
sources=sorted(df.source.dropna().unique().tolist())
leagues=sorted(df.league.dropna().unique().tolist())
selected_sources=st.multiselect("Data sources",sources,default=sources)
selected_leagues=st.multiselect("Leagues",leagues,default=leagues)
years=sorted(df.season_year.dropna().astype(int).unique().tolist())
if years:
    year_range=st.slider("Calendar years",min(years),max(years),(min(years),max(years)))
    view=df[df.source.isin(selected_sources)&df.league.isin(selected_leagues)&df.season_year.between(*year_range)].copy()
else:
    view=df.iloc[0:0].copy()

st.subheader("Source totals")
st.dataframe(view.groupby("source",as_index=False)[metrics].sum(),hide_index=True,use_container_width=True)
st.subheader("League and calendar-year coverage")
columns=["source","league","season_year"]+metrics
st.dataframe(view[columns].sort_values(["source","league","season_year"]),hide_index=True,use_container_width=True)
st.download_button("Export coverage CSV",view[columns].to_csv(index=False).encode("utf-8"),
    file_name="starlizard_archive_coverage.csv",mime="text/csv")

st.subheader("Research readiness")
st.markdown("""
- **Goals:** Full-time and half-time score coverage is shown above.
- **Corners and cards:** Coverage reflects whether the source recorded the fields, not their accuracy.
- **Pre-match odds:** Bet365 odds coverage is not the same as live or half-time market prices.
- **xG and goal sequence:** Understat verified sequences are tracked separately. Half-time xG uses a provisional timing convention.
- **Cross-source analyses:** Only linked matches should combine Understat xG with football-data odds, corners or cards. Do not add match counts across sources; they overlap.
""")
