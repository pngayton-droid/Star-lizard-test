"""PRO STARLIZARD — unified historical model intelligence dashboard.
Read-only; descriptive signals are not betting recommendations.
"""
import streamlit as st
import pandas as pd
from archive_data_engine import load_coverage, load_research
from pattern_intelligence_engine import run_pattern_scan
from pattern_history_store import save_snapshot, list_snapshots, load_snapshot

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

st.subheader("Automatic research findings")
st.caption("Same shared scan as Automatic Pattern Scanner: chronological 70/30 split, minimum 80 matches per segment and period.")
@st.cache_data(ttl=900)
def get_findings(frame):
    return run_pattern_scan(frame,min_n=80,split=0.7)
findings=get_findings(matches)
if findings.empty:
    st.info("No sufficiently large segments were found.")
else:
    x,y,z=st.columns(3)
    x.metric("Segments scanned",len(findings))
    y.metric("Direction replicated",int(findings.replicated_direction.sum()))
    z.metric("Exploratory flags",int(findings.screen_flag.sum()))
    shown=findings[findings.screen_flag].copy()
    if shown.empty:
        st.info("No segments passed the current exploratory screen; this is a valid outcome.")
    else:
        st.dataframe(shown,hide_index=True,use_container_width=True)
    with st.expander("All scanned segments"):
        st.dataframe(findings,hide_index=True,use_container_width=True)
    st.download_button("Export intelligence findings",findings.to_csv(index=False).encode("utf-8"),
                       "starlizard_intelligence_findings.csv",mime="text/csv")
st.caption("Exploratory findings only: no half-time/live market odds, commissions or prospective validation. No profitability inferred.")

st.subheader("Pattern tracking history")
st.caption("Save an immutable research snapshot. Identical data and scan settings reuse the same snapshot ID.")
settings={"min_n":80,"split":0.7,"segments":["league","home_price_band","away_price_band"]}
if st.button("Save current pattern scan",type="primary"):
    try:
        key=save_snapshot(matches,findings,settings)
        st.success("Research snapshot recorded (or already saved): "+key[:12])
        st.cache_data.clear()
    except Exception as exc:
        st.error("Snapshot could not be saved.")
        st.code(str(exc))
try:
    history=list_snapshots()
except Exception as exc:
    st.warning("Pattern history is not currently available.")
    history=pd.DataFrame()
if not history.empty:
    st.dataframe(history[["created_at","match_count","segment_count","flagged_count","scan_version"]],hide_index=True,use_container_width=True)
    options=history.scan_key.tolist()
    selected=st.selectbox("Inspect saved research snapshot",options,format_func=lambda k:
        str(history.loc[history.scan_key==k,"created_at"].iloc[0])+" · "+k[:10])
    if selected:
        try:
            snapshot=load_snapshot(selected)
            if snapshot:
                prior=pd.DataFrame(snapshot["results"])
                st.caption("Saved with "+str(snapshot["match_count"])+" linked matches.")
                if not prior.empty:
                    st.dataframe(prior,hide_index=True,use_container_width=True)
                    st.download_button("Export saved snapshot",prior.to_csv(index=False).encode("utf-8"),
                        "starlizard_saved_pattern_scan.csv","text/csv")
        except Exception as exc:
            st.warning("Could not load selected snapshot.")
else:
    st.info("No saved scans yet. Use the button above to record the first baseline.")

st.subheader("Research pipeline")
st.markdown("""
**Available now:** Historical archive, coverage reporting, linked-match research,
next-goal screening and exploratory automatic pattern scanning.

**Still required before production signals:** Reliable half-time timing conventions,
market-specific historical odds, out-of-sample validation, transaction costs,
and monitored data freshness.
""")
st.info("This dashboard summarizes data readiness. Findings are computed from cached archive data, not stored as validated strategies.")
st.download_button("Export readiness report",readiness.to_csv(index=False).encode("utf-8"),
                   "starlizard_model_readiness.csv",mime="text/csv")
