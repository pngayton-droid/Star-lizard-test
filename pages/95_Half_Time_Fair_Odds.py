"""PRO STARLIZARD half-time betting dashboard: live fixture picker and historical research."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import streamlit as st
import pandas as pd
from lightweight_fixture_feed import get_key, fixtures_for_day, fixture_label, team_name
from statsapi_refresh import LEAGUES
from halftime_research_engine import halftime_sample
from halftime_snapshot_pricing import OUTCOMES, snapshot_research

st.set_page_config(page_title="The Match Matrix | Half-Time",page_icon="⚽",layout="wide")
st.markdown("""
<style>
[data-testid="stAppViewContainer"] {background:linear-gradient(160deg,rgba(218,41,28,.13),transparent 340px)}
h1,h2,h3{letter-spacing:-.025em} h1{color:#da291c!important}
div.stButton>button[kind="primary"]{background-color:#da291c;color:white}
.hero{background:linear-gradient(110deg,#8b1114,#da291c 72%,#a41918);color:white;
border-left:6px solid #fbe122;border-bottom:3px solid #da291c;padding:15px 16px;
border-radius:10px;margin-bottom:14px}
.hero h2{color:white!important;margin:0;font-size:clamp(1.7rem,5vw,3rem)}
.hero p{color:#fff4df;margin:5px 0}\n.hero img{float:right;width:clamp(155px,30vw,230px);height:230px;object-fit:contain;margin:0 0 4px 12px}\n.hero:after{content:"";display:block;clear:both}
</style>
<div class="hero"><img src="https://en.wikinews.org/wiki/Special:FilePath/Manchester_United_F.C._logo.svg" alt="Manchester United crest" /><h2>THE MATCH MATRIX</h2>
<p>HALF-TIME BETTING INTELLIGENCE · GOALS · NEXT GOAL · SECOND-HALF RESULT</p></div>
""",unsafe_allow_html=True)
st.title("Half-Time Match Centre")
st.caption("Choose today's fixture, enter the observed half-time statistics, then inspect historical second-half probabilities.")
key=get_key()
if not key:
    st.error("TheStatsAPI key is missing from Streamlit secrets.")
    st.stop()
today=datetime.now(ZoneInfo("Europe/London")).date()
day=st.date_input("Fixture date",today,min_value=today-timedelta(days=7),max_value=today+timedelta(days=21))
try:
    fixtures=fixtures_for_day(key,day.isoformat())
except Exception as exc:
    st.error("Could not retrieve fixtures from TheStatsAPI.")
    st.caption(type(exc).__name__)
    st.stop()
allowed=set(LEAGUES.values())
def comp_id(f):
    competition=f.get("competition")
    return str(f.get("competition_id") or (competition.get("id") if isinstance(competition,dict) else "") or "")
fixtures=[f for f in fixtures if comp_id(f) in allowed]
fixtures=sorted(fixtures,key=fixture_label)
if not fixtures:
    st.info("No fixtures in the selected leagues on this date.")
    st.stop()
chosen=st.selectbox("Today's fixtures — select a match",range(len(fixtures)),format_func=lambda i:fixture_label(fixtures[i]))
fixture=fixtures[chosen]
st.subheader(f"{team_name(fixture,'home')} v {team_name(fixture,'away')}")
if st.session_state.get("selected_ht_fixture")!=str(fixture.get("id")):
    for k in ("ht_home_goals","ht_away_goals","ht_home_xg","ht_away_xg","ht_market_result"):
        st.session_state.pop(k,None)
    st.session_state["selected_ht_fixture"]=str(fixture.get("id"))
st.caption("TheStatsAPI status: "+str(fixture.get("status","Unknown")))
score=fixture.get("score") or {}
home_default=score.get("home")
away_default=score.get("away")
a,b=st.columns(2)
with a:
    home_goals=st.number_input("Home HT goals",min_value=0,max_value=12,value=int(home_default) if isinstance(home_default,int) else 0,key="ht_home_goals")
    home_xg=st.number_input("Home first-half xG",min_value=0.0,max_value=10.0,value=0.8,step=0.05,key="ht_home_xg")
with b:
    away_goals=st.number_input("Away HT goals",min_value=0,max_value=12,value=int(away_default) if isinstance(away_default,int) else 0,key="ht_away_goals")
    away_xg=st.number_input("Away first-half xG",min_value=0.0,max_value=10.0,value=0.6,step=0.05,key="ht_away_xg")
st.caption("Confirm the half-time score and xG manually. Live API score fields may reflect full-time or an in-play score, not half-time.")
tolerance=st.slider("Historical xG similarity range",0.2,1.5,0.5,0.1)
markets=[
"Second half: at least 1 goal","Second half: at least 2 goals","Second half: at least 3 goals",
"Home scores in second half","Away scores in second half","Both teams score in second half",
"Home wins second half","Second half draw","Away wins second half"]
if st.button("Calculate second-half historical prices",type="primary",use_container_width=True):
    with st.spinner("Checking matching historical half-time situations…"):
        try:
            rows=halftime_sample(None)
            output=[]
            for market in markets:
                result=snapshot_research(rows,int(home_goals),int(away_goals),float(home_xg),float(away_xg),market,float(tolerance))
                if result["status"]=="Research estimate available":
                    p=result["train_rate"]
                    output.append({"Second-half market":market,"Historical probability":f"{100*p:.1f}%",
                      "Descriptive decimal odds":f"{1/p:.2f}" if p>0 else "—",
                      "Earlier sample":result["train_n"],"Later sample":result["later_n"],
                      "Later observed rate":f'{100*result["later_rate"]:.1f}%'})
                else:
                    output.append({"Second-half market":market,"Historical probability":"Insufficient sample",
                      "Descriptive decimal odds":"—","Earlier sample":result.get("train_n",0),
                      "Later sample":result.get("later_n",0),"Later observed rate":"—"})
            st.session_state["ht_market_result"]=(str(fixture.get("id")),int(home_goals),int(away_goals),float(home_xg),float(away_xg),float(tolerance),output)
        except Exception as exc:
            st.error("Historical halftime comparison unavailable: "+str(exc)[:160])
snapshot=st.session_state.get("ht_market_result")
identity=(str(fixture.get("id")),int(home_goals),int(away_goals),float(home_xg),float(away_xg),float(tolerance))
if snapshot and snapshot[:6]==identity:
    st.subheader("Second-half historical prices")
    st.dataframe(pd.DataFrame(snapshot[6]),hide_index=True,use_container_width=True)
st.warning("These are descriptive historical frequencies, NOT the trained A0 model's live fair odds. The verified model must still be fitted and deployed for fixture-specific prices. No bookmaker value or ROI is claimed.")
