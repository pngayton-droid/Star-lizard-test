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
st.caption("Choose today's fixture, enter the observed half-time statistics, then calculate modelled second-half fair odds.")
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
st.subheader("Pre-match market prices (model strength input)")
st.caption("Enter genuine pre-match 1X2 decimal prices. These are model inputs, not halftime bookmaker quotes.")
p1,p2,p3=st.columns(3)
with p1: home_price=st.number_input("Home",min_value=1.01,max_value=1000.0,value=2.50,step=0.05)
with p2: draw_price=st.number_input("Draw",min_value=1.01,max_value=1000.0,value=3.30,step=0.05)
with p3: away_price=st.number_input("Away",min_value=1.01,max_value=1000.0,value=3.00,step=0.05)
st.subheader("First-half match events")
a,b=st.columns(2)
with a:
    hs=st.number_input("Home shots",0,80,5)
    hst=st.number_input("Home shots on target",0,80,2)
    hc=st.number_input("Home corners",0,50,2)
    hr=st.number_input("Home red cards",0,5,0)
with b:
    ats=st.number_input("Away shots",0,80,5)
    ast=st.number_input("Away shots on target",0,80,2)
    ac=st.number_input("Away corners",0,50,2)
    ar=st.number_input("Away red cards",0,5,0)
st.caption("Use actual first-half events; default numbers are placeholders, not live StatsAPI data.")
if hst>hs or ast>ats:
    st.error("Shots on target cannot exceed total shots.")
    st.stop()
import io
import requests
import joblib
import numpy as np
@st.cache_resource(ttl=3600,show_spinner=False)
def load_model():
    url="https://raw.githubusercontent.com/pngayton-droid/Star-lizard-test/main/model_artifacts/halftime_second_half_models.joblib"
    response=requests.get(url,timeout=30)
    response.raise_for_status()
    return joblib.load(io.BytesIO(response.content))
inputs=(str(fixture.get("id")),int(home_goals),int(away_goals),float(home_xg),float(away_xg),
        float(home_price),float(draw_price),float(away_price),hs,hst,hc,hr,ats,ast,ac,ar)
if st.button("Calculate trained model fair odds",type="primary",use_container_width=True):
    try:
        model=load_model()
        inverse=np.array([1/home_price,1/draw_price,1/away_price])
        ph,p_draw,pa=inverse/inverse.sum()
        diff=home_goals-away_goals
        features={"home_ht_goals":home_goals,"away_ht_goals":away_goals,
            "p_home":ph,"p_draw":p_draw,"p_away":pa,"ht_diff":diff,
            "ht_total":home_goals+away_goals,"score_strength":diff*(ph-pa),
            "h_shots":hs,"a_shots":ats,"h_sot":hst,"a_sot":ast,
            "h_corners":hc,"a_corners":ac,"h_red":hr,"a_red":ar,
            "home_ht_xg":home_xg,"away_ht_xg":away_xg}
        X=pd.DataFrame([features])[model["feature_columns"]]
        scaled=model["scaler"].transform(X)
        names={"next_goal":"Next goal","second_half_result":"2H result",
               "over_0_5_2h":"Over 0.5","over_1_5_2h":"Over 1.5",
               "over_2_5_2h":"Over 2.5","home_scores_2h":"Home scores",
               "away_scores_2h":"Away scores","both_score_2h":"Both score"}
        outcomes={"0":"No","1":"Yes","home":"Home","away":"Away",
                  "draw":"Draw","none":"No goal"}
        # Coherence layer: reconcile independently fitted market probabilities.
        # This is a post-processing constraint, not retraining or a claim of better calibration.
        probs={}
        for market,clf in model["models"].items():
            probs[market]={str(k):float(v) for k,v in zip(clf.classes_,clf.predict_proba(scaled)[0])}
        raw={k:dict(v) for k,v in probs.items()}
        # Nested goal totals cannot increase with a higher threshold.
        o05=probs["over_0_5_2h"]["1"]
        o15=min(probs["over_1_5_2h"]["1"],o05)
        o25=min(probs["over_2_5_2h"]["1"],o15)
        for k,p in (("over_0_5_2h",o05),("over_1_5_2h",o15),("over_2_5_2h",o25)):
            probs[k]={"1":p,"0":1-p}
        # No next goal is exactly no second-half goals. Preserve the learned
        # home/away next-goal ratio conditional on at least one goal.
        nextp=probs["next_goal"]
        hshare=nextp["home"]/max(nextp["home"]+nextp["away"],1e-12)
        probs["next_goal"]={"home":o05*hshare,"away":o05*(1-hshare),"none":1-o05}
        # Both sides scoring implies each side scores and at least two total goals.
        both=min(probs["both_score_2h"]["1"],
                 probs["home_scores_2h"]["1"],probs["away_scores_2h"]["1"],o15)
        probs["both_score_2h"]={"1":both,"0":1-both}
        # Inclusion-exclusion: P(H scores)+P(A scores)-P(both) <= P(any goal).
        # Adjust individual scoring chances down only when necessary.
        h=probs["home_scores_2h"]["1"];a=probs["away_scores_2h"]["1"]
        excess=max(0.0,h+a-both-o05)
        if excess:
            room_h=max(0.0,h-both);room_a=max(0.0,a-both)
            take_h=min(room_h,excess*room_h/max(room_h+room_a,1e-12))
            h-=take_h;a-=min(room_a,excess-take_h)
        probs["home_scores_2h"]={"1":h,"0":1-h}
        probs["away_scores_2h"]={"1":a,"0":1-a}
        # A scoreless second half necessarily finishes as a second-half draw.
        draw=probs["second_half_result"]["draw"]
        if draw<1-o05:
            other=probs["second_half_result"]["home"]+probs["second_half_result"]["away"]
            factor=o05/max(other,1e-12)
            probs["second_half_result"]={"home":probs["second_half_result"]["home"]*factor,
                                         "away":probs["second_half_result"]["away"]*factor,
                                         "draw":1-o05}
        adjustments=sum(abs(probs[k].get(sel,0)-v)>1e-8 for k,vals in raw.items() for sel,v in vals.items())
        rows=[]
        for market,values in probs.items():
            for selection,p in values.items():
                label=names[market]
                if market in ("next_goal","second_half_result"):
                    label+=": "+outcomes[str(selection)]
                elif str(selection)!="1":continue
                rows.append({"Market":label,"Chance":f"{100*p:.1f}%",
                             "Fair odds":f"{1/p:.2f}" if p>0 else "—"})
        st.session_state["trained_ht_result"]=(inputs,rows,model["training_rows"],model["last_training_date"])
    except Exception as exc:
        st.error("Trained model not available yet. The export workflow may still be running.")
        st.caption(type(exc).__name__+": "+str(exc)[:120])
result=st.session_state.get("trained_ht_result")
if result and result[0]==inputs:
    st.subheader("Modelled second-half fair odds")
    st.dataframe(pd.DataFrame(result[1]),hide_index=True,use_container_width=True,
                 height=min(540,35*(len(result[1])+1)))
    st.caption(f"Trained on {result[2]:,} verified matches through {result[3]}. Probabilities reconciled for logical consistency; this does not establish better accuracy or betting value. Fair odds exclude bookmaker margin.")

with st.expander("Model validation — 2,000-match retrospective holdout",expanded=False):
    st.caption("The final 2,000 chronological walk-forward fixtures are evaluated separately from earlier development predictions. This split was selected after earlier results had been reviewed; it is not a fresh untouched holdout.")
    try:
        import requests as _requests
        import io as _io
        _url="https://raw.githubusercontent.com/pngayton-droid/Star-lizard-test/main/research_results/ht_second_half_fair_odds_summary.csv"
        _r=_requests.get(_url,timeout=12)
        _r.raise_for_status()
        _scores=pd.read_csv(_io.StringIO(_r.text))
        _hold=_scores[_scores["split"]=="holdout_2000"]
        if len(_hold):
            st.dataframe(_hold[["market","fixtures","logloss"]].rename(columns={"market":"Market","fixtures":"Matches","logloss":"Log loss"}),
                         hide_index=True,use_container_width=True)
        else:
            st.info("The 2,000-match holdout results are being generated. The previous 369-match split is no longer the target.")
    except Exception:
        st.info("Holdout results not yet available. Please check again after the research workflow completes.")

st.warning("Experimental fixture-specific model probabilities, not proven betting value. Enter verified halftime data and genuine pre-match odds; do not use placeholder values.")
