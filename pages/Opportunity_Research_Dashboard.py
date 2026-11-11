"""PRO STARLIZARD — research opportunity watchlist (not betting signals)."""
import pandas as pd
import streamlit as st
from archive_data_engine import load_research
from pattern_validation_engine import validate_patterns
from pricing_comparison_engine import quote_comparison

st.set_page_config(page_title="Opportunity Research Dashboard",layout="wide")
st.title("🦎 Opportunity Research Dashboard")
st.caption("A watchlist of historical patterns with optional market-quote comparisons. No fixture-level signals or automated bets.")

@st.cache_data(ttl=900)
def get_archive():
    return load_research()

@st.cache_data(ttl=900)
def get_audit(frame):
    return validate_patterns(frame,min_n=80,split=0.7)

try:
    matches=get_archive()
    findings=get_audit(matches)
except Exception as exc:
    st.error("Historical research could not be loaded.")
    st.code(str(exc))
    st.stop()

if findings.empty:
    st.info("No research segments currently meet the scan requirements.")
    st.stop()

confirmed=findings[findings.holdout_confirmed.fillna(False).astype(bool)].copy()
a,b,c=st.columns(3)
a.metric("Historical segments",len(findings))
b.metric("Discovery flags",int(findings.screen_flag.fillna(False).sum()))
c.metric("Holdout confirmations",len(confirmed))
st.warning("Historical confirmation is not proof of betting value. This dashboard does not yet know upcoming fixtures or current bookmaker prices.")

st.subheader("Research watchlist")
status=st.radio("Show",["Holdout-confirmed only","All audited segments"],horizontal=True)
market_choices=sorted(findings.market.dropna().unique().tolist())
markets=st.multiselect("Markets",market_choices,default=market_choices)
table=(confirmed if status=="Holdout-confirmed only" else findings).copy()
table=table[table.market.isin(markets)]
if table.empty:
    st.info("No segments match these filters. Choose 'All audited segments' to inspect research candidates.")
else:
    columns=["market","segment","value","train_n","holdout_n","holdout_rate",
             "holdout_rest_rate","holdout_q","screen_flag","holdout_confirmed"]
    st.dataframe(table[columns],hide_index=True,use_container_width=True)
    st.download_button("Export watchlist",table.to_csv(index=False).encode("utf-8"),
                       "starlizard_research_watchlist.csv",mime="text/csv")

st.subheader("Quote comparison workspace")
st.caption("Enter an actual market quote manually. Results describe historical frequencies only, not a future fixture probability.")
if table.empty:
    st.info("Choose at least one watchlist segment above.")
else:
    table=table.reset_index(drop=True)
    table["display"]=table.apply(lambda r:
        str(r.market)+" | "+str(r.segment)+" = "+str(r.value)+
        " | n="+str(int(r.holdout_n)),axis=1)
    choice=st.selectbox("Segment",range(len(table)),format_func=lambda i:table.iloc[i]["display"])
    selected=table.iloc[choice]
    quote=st.number_input("Decimal market odds",min_value=1.01,max_value=1000.0,value=2.0,step=0.05)
    commission=st.number_input("Commission on net winnings (%)",min_value=0.0,max_value=30.0,value=0.0,step=0.5)
    hits=int(selected.holdout_segment_hits)
    n=int(selected.holdout_n)
    values=quote_comparison(hits,n,quote,commission)
    x,y,z=st.columns(3)
    x.metric("Observed rate",f'{values["observed_rate"]*100:.1f}%')
    y.metric("Quote break-even",f'{values["break_even_rate"]*100:.1f}%')
    z.metric("Historical return illustration",f'{values["historical_return"]*100:+.1f}%')
    st.write(f'95% descriptive interval: **{values["lower_rate"]*100:.1f}%–{values["upper_rate"]*100:.1f}%**')
    st.write(f'Lower-bound historical return illustration: **{values["lower_bound_return"]*100:+.1f}%**')
    if not bool(selected.holdout_confirmed):
        st.warning("This segment did not pass the later-period confirmation screen.")
    st.info("No value-bet alert is issued: subgroup averages do not account for the selected fixture, market efficiency, selection effects, execution, or future calibration.")

st.subheader("Before live opportunities")
st.markdown("""Upcoming fixture and market feeds, reliable timestamped odds, calibrated match-specific probabilities, transaction costs, and prospective monitoring are required before the dashboard can show actionable model signals.""")
