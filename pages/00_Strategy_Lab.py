"""New mobile-first entry point for odds-backed research. Read-only, no API calls."""
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="PRO STARLIZARD | Strategy Lab", page_icon="🦎", layout="wide")
st.markdown("""<style>
.block-container {max-width: 1050px; padding-top: 1.4rem}
div[data-testid="stMetric"] {border:1px solid #44515c55; border-radius:14px; padding:12px}
@media(max-width:650px){.block-container{padding-left:1rem;padding-right:1rem} h1{font-size:1.9rem!important}}
</style>""", unsafe_allow_html=True)
st.title("🦎 PRO STARLIZARD")
st.subheader("Strategy Lab")
st.caption("Find strategies with historical odds, verified outcomes and independent profitability tests.")
st.info("New interface preview. Your existing database, collectors and research pages remain untouched.")
@st.cache_data(ttl=3600)
def coverage():
    db = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])
    names = ["btts", "total_goals", "match_corners", "total_cards", "first_half_result", "asian_handicap"]
    counts = {n:0 for n in names}
    for start in range(0, 20000, 500):
        batch = (db.table("historical_match_odds").select("odds_payload")
                 .eq("fetch_status","collected").range(start,start+499).execute()).data or []
        for item in batch:
            markets = set()
            for book in (item.get("odds_payload") or {}).get("data",{}).get("bookmakers",[]) or []:
                markets.update((book.get("markets") or {}).keys())
            for n in names:
                counts[n] += n in markets
        if len(batch) < 500: break
    return counts
st.markdown("### Available research markets")
try:
    counts = coverage()
    labels = {"btts":"Both teams to score","total_goals":"Total goals","match_corners":"Match corners",
              "total_cards":"Total cards","first_half_result":"First-half result","asian_handicap":"Asian handicap"}
    for key,label in labels.items():
        with st.container(border=True):
            left,right=st.columns([3,1])
            left.markdown(f"**{label}**")
            right.markdown(f"**{counts[key]:,}**")
            st.caption("Matches with stored odds · settlement and timing still require verification")
except Exception as exc:
    st.warning("Odds coverage unavailable. Check database connection.")
st.markdown("### Our testing rules")
st.markdown("**1.** Historical price + verified outcome required.  \n**2.** Use only information available when the bet was placed.  \n**3.** Train on earlier matches; test on untouched later matches.  \n**4.** Report stake-based profit, ROI, drawdown and bet count.  \n**5.** Never label a historical quote as guaranteed executable.")
st.markdown("### Existing research (preserved)")
st.page_link("pages/Historical_Odds_Backtest.py",label="Open existing odds backtest",icon="📈")
st.page_link("pages/10_Halftime_Research.py",label="Open halftime outcome research",icon="🔎")
st.caption("Next build: verified settlement engine and multi-market strategy scanner. No profitability results are claimed on this page.")
