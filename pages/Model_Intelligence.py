"""PRO STARLIZARD — unified historical model intelligence dashboard.
Read-only; descriptive signals are not betting recommendations.
"""
import streamlit as st
import pandas as pd
from archive_data_engine import load_coverage, load_research

st.set_page_config(page_title="Model Intelligence", layout="wide")
st.title("🦎 PRO STARLIZARD | Model Intelligence")
st.caption("Historical model control centre · Read-only · No betting edge claims")

@st.cache_data(ttl=900)
def get_data():
    return load_coverage(), load_research()

try:
    coverage, matches = get_data()
except Exception as exc:
    st.error("Private historical data is unavailable. Check server credentials and database views.")
    st.code(str(exc))
    st.stop()
if coverage.empty or matches.empty:
    st.warning("Archive coverage or linked research data is empty.")
    st.stop()

for field in ["matches","ft_scores","ht_scores","corners","yellow_cards","b365_odds","verified_sequences","linked_matches"]:
    coverage[field] = pd.to_numeric(coverage[field], errors="coerce").fillna(0).astype(int)
for field in ["verified_goal_sequence","has_ht_score","has_corners","has_yellows","has_b365_odds"]:
    matches[field] = matches[field].fillna(False).astype(bool)
matches["match_date"] = pd.to_datetime(matches["match_date"],errors="coerce")
matches = matches.drop_duplicates(subset=["understat_id"])

sources = coverage.groupby("source",as_index=True).sum(numeric_only=True)
def total(source, field):
    return int(sources.loc[source,field]) if source in sources.index else 0

st.subheader("Archive status")
a,b,c,d=st.columns(4)
a.metric("Football-data",f"{total('Football-data','matches'):,}")
b.metric("Understat",f"{total('Understat','matches'):,}")
c.metric("Linked matches",f"{len(matches):,}")
d.metric("Verified linked sequences",f"{int(matches.verified_goal_sequence.sum()):,}")
st.caption("Source totals overlap; do not add them to estimate unique matches.")

st.subheader("Research readiness")
requirements = {
    "Goals + half-time scores": matches.has_ht_score,
    "Corners": matches.has_corners,
    "Yellow cards": matches.has_yellows,
    "Bet365 pre-match odds": matches.has_b365_odds,
    "Verified goal sequence": matches.verified_goal_sequence,
    "Verified sequence + HT + pre-match odds": (
        matches.verified_goal_sequence & matches.has_ht_score & matches.has_b365_odds),
}
readiness=pd.DataFrame([
    {"dataset":name,"linked_matches":int(mask.sum()),"coverage_pct":round(100*mask.mean(),1)}
    for name,mask in requirements.items()
])
st.dataframe(readiness,hide_index=True,use_container_width=True)
st.caption("Coverage means a field is recorded, not that every value is independently audited.")

st.subheader("League coverage")
league_counts=(matches.groupby("league",dropna=False).agg(
    linked_matches=("understat_id","size"),
    verified_sequences=("verified_goal_sequence","sum"),
    with_corners=("has_corners","sum"),
    with_cards=("has_yellows","sum"),
    with_odds=("has_b365_odds","sum")
).reset_index().sort_values("linked_matches",ascending=False))
st.dataframe(league_counts,hide_index=True,use_container_width=True)

st.subheader("Calendar-year coverage")
matches["year"]=matches.match_date.dt.year
year_counts=matches.groupby("year",dropna=False).agg(
    linked_matches=("understat_id","size"),
    verified_sequences=("verified_goal_sequence","sum")
).reset_index().sort_values("year")
st.bar_chart(year_counts.set_index("year")["linked_matches"])
with st.expander("Year-by-year table"):
    st.dataframe(year_counts,hide_index=True,use_container_width=True)

st.subheader("Research pipeline")
st.markdown("""
**Available now:** Historical archive, coverage reporting, linked-match research,
next-goal screening and exploratory automatic pattern scanning.

**Still required before production signals:** Reliable half-time timing conventions,
market-specific historical odds, out-of-sample validation, transaction costs,
and monitored data freshness.
""")
st.info("This dashboard summarizes data readiness. It does not claim that any strategy is profitable or that pattern scanner results are persisted.")
st.download_button("Export readiness report",readiness.to_csv(index=False).encode("utf-8"),
                   "starlizard_model_readiness.csv",mime="text/csv")
