"""PRO STARLIZARD 2.0 — existing TheStatsAPI records only.
Read-only Supabase dashboard. No calls to TheStatsAPI; no new leagues downloaded.
Run with: streamlit run starlizard_2.py
"""
import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(page_title="PRO STARLIZARD 2.0", page_icon="⚽", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
.stApp{background:#0b1220;color:#edf3ff}
.block-container{max-width:1150px;padding-top:1.8rem}
div[data-testid="stMetric"]{background:#172238;padding:15px;border-radius:12px;border:1px solid #33435c}
</style>""", unsafe_allow_html=True)
st.image("pro_starlizard_header_correct-1.png", use_container_width=True)
st.title("PRO STARLIZARD 2.0")
st.caption("Existing TheStatsAPI data only · Read-only research · No new API collection")

@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])

@st.cache_data(ttl=900)
def total(table):
    return db().table(table).select("match_id", count="exact").limit(1).execute().count or 0

@st.cache_data(ttl=900)
def league_inventory():
    # Query only existing database rows; aggregate from locally stored xG history.
    # Fetch all pages rather than silently treating the first 1,000 as the full archive.
    rows=[]
    for offset in range(0, 100000, 1000):
        batch=(db().table("historical_xg")
               .select("match_id,competition_id,match_date")
               .order("match_id")
               .range(offset,offset+999).execute().data or [])
        rows.extend(batch)
        if len(batch)<1000:
            break
    if not rows:
        return pd.DataFrame(columns=["League ID","Matches","First match","Last match"])
    df=pd.DataFrame(rows).drop_duplicates("match_id")
    df["match_date"]=pd.to_datetime(df["match_date"],errors="coerce")
    out=(df.groupby("competition_id",dropna=False)
         .agg(Matches=("match_id","count"),first=("match_date","min"),last=("match_date","max"))
         .reset_index().rename(columns={"competition_id":"League ID","first":"First match","last":"Last match"}))
    return out.sort_values("Matches",ascending=False)

LEAGUE_NAMES = {
    "comp_8321":"England · Championship",
    "comp_3039":"England · Premier League",
    "comp_5840":"Italy · Serie A",
    "comp_8814":"Spain · La Liga",
    "comp_0256":"France · Ligue 1",
    "comp_4643":"Germany · Bundesliga",
    "comp_8531":"Belgium · Pro League",
    "comp_3809":"Netherlands · Eredivisie",
    "comp_8385":"Portugal · Primeira Liga",
    "comp_6387":"Scotland · Premiership",
}

tab1,tab2,tab3=st.tabs(["🏠 Overview","🏆 Existing leagues","📊 Data coverage"])
with tab1:
    st.subheader("Our existing football database")
    try:
        a,b,c=st.columns(3)
        a.metric("Event timeline records",f"{total('historical_match_events'):,}")
        b.metric("Historical odds records",f"{total('historical_match_odds'):,}")
        c.metric("Historical xG records",f"{total('historical_xg'):,}")
    except Exception as exc:
        st.error(f"Database connection unavailable: {type(exc).__name__}")
    st.info("No fresh API requests are made by this dashboard. Existing collectors and credentials are unchanged.")
    st.warning("No betting edge is currently verified by this dashboard. Prices and signals must pass out-of-sample testing.")
with tab2:
    st.subheader("Leagues already in our stored data")
    try:
        leagues=league_inventory()
        leagues.insert(0,"League",leagues["League ID"].map(LEAGUE_NAMES).fillna("Unassigned"))
        st.metric("Identified leagues",int(leagues["League ID"].notna().sum()))
        selection = st.multiselect(
            "Compare leagues",
            options=leagues["League"].tolist(),
            default=leagues["League"].tolist(),
        )
        selected = leagues[leagues["League"].isin(selection)].copy()
        st.dataframe(selected,use_container_width=True,hide_index=True)
        if not selected.empty:
            st.bar_chart(selected.set_index("League")["Matches"],horizontal=True)
            st.metric("Matches in selected leagues",f"{int(selected['Matches'].sum()):,}")
        st.caption("Inventory comes from historical_xg; event/odds coverage can differ. No leagues are fetched from TheStatsAPI.")
    except Exception as exc:
        st.error(f"League inventory unavailable: {type(exc).__name__}")
@st.cache_data(ttl=900)
def coverage_ids(table):
    ids = set()
    for offset in range(0, 100000, 1000):
        batch = (db().table(table).select("match_id")
                 .order("match_id").range(offset, offset + 999).execute().data or [])
        ids.update(str(row["match_id"]) for row in batch if row.get("match_id") is not None)
        if len(batch) < 1000:
            break
    return ids

@st.cache_data(ttl=900)
def coverage_by_league():
    odds_ids = coverage_ids("historical_match_odds")
    event_ids = coverage_ids("historical_match_events")
    rows = []
    for offset in range(0, 100000, 1000):
        batch = (db().table("historical_xg")
                 .select("match_id,competition_id,home_xg,away_xg,home_ht_xg,away_ht_xg")
                 .order("match_id").range(offset, offset + 999).execute().data or [])
        for m in batch:
            match_id = str(m["match_id"])
            rows.append({
                "League": LEAGUE_NAMES.get(m.get("competition_id"), "Unassigned"),
                "Match ID": match_id,
                "Odds stored": int(match_id in odds_ids),
                "Events stored": int(match_id in event_ids),
                "Full-time xG": int(m.get("home_xg") is not None and m.get("away_xg") is not None),
                "Half-time xG": int(m.get("home_ht_xg") is not None and m.get("away_ht_xg") is not None),
            })
        if len(batch) < 1000:
            break
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows).drop_duplicates("Match ID")
    return (frame.groupby("League", as_index=False)
            .agg(Matches=("Match ID", "count"),
                 Odds_records=("Odds stored", "sum"),
                 Event_records=("Events stored", "sum"),
                 FT_xG=("Full-time xG", "sum"),
                 HT_xG=("Half-time xG", "sum"))
            .sort_values("Matches", ascending=False))

with tab3:
    st.subheader("Stored match data coverage")
    st.caption("Matches joined by match ID across existing Supabase tables. Odds record presence does not guarantee usable prices.")
    if st.button("Run read-only coverage audit", type="primary"):
        try:
            report = coverage_by_league()
            st.dataframe(report, use_container_width=True, hide_index=True)
            st.download_button("Download coverage CSV", report.to_csv(index=False), "starlizard_coverage.csv", "text/csv")
        except Exception as exc:
            st.error(f"Coverage audit failed: {type(exc).__name__}: {exc}")
    st.info("No external StatsAPI requests. The audit reads stored Supabase records only.")
