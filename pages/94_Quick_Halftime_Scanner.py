"""Mobile-first halftime scanner. Read-only API; existing pricing page stays unchanged."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import joblib
from pathlib import Path
import numpy as np
import pandas as pd
import requests
import streamlit as st
from lightweight_fixture_feed import get_key, fixtures_for_day, fixture_label, team_name, API_BASE
from statsapi_refresh import LEAGUES
from fixture_live_status import fixture_status

st.set_page_config(page_title="Match Matrix | Quick Scanner", page_icon="⚽", layout="wide")
st.title("⚽ THE MATCH MATRIX")
st.markdown("""<style>div[data-testid="stNumberInput"] label p{font-size:.78rem} div[data-testid="stVerticalBlock"]{gap:.55rem} h1{font-size:1.55rem!important} h2,h3{font-size:1.15rem!important}</style>""",unsafe_allow_html=True)
st.caption("Quick halftime scanner · live StatsAPI facts · no guessed statistics or bookmaker prices")
key = get_key()
if not key:
    st.error("Missing TheStatsAPI key in Streamlit secrets.")
    st.stop()
day = st.date_input("Match date", datetime.now(ZoneInfo("Europe/London")).date(),
                    min_value=datetime.now(ZoneInfo("Europe/London")).date()-timedelta(days=7),
                    max_value=datetime.now(ZoneInfo("Europe/London")).date()+timedelta(days=14))
try:
    all_fixtures = fixtures_for_day(key, day.isoformat())
except Exception as exc:
    st.error(f"Fixture feed unavailable: {type(exc).__name__}")
    st.stop()
allowed = set(LEAGUES.values())
def comp_id(f):
    c=f.get("competition") or {}
    return str(f.get("competition_id") or (c.get("id") if isinstance(c,dict) else "") or "")
fixtures = sorted([f for f in all_fixtures if comp_id(f) in allowed], key=fixture_label)
st.caption(f"{len(fixtures)} fixtures in selected leagues · fixture feed cached for 60 seconds")
if not fixtures:
    st.info("No selected-league fixtures today.")
    st.stop()
status_filter = st.radio("Show", ["All", "Half-time / live", "Finished"], horizontal=True)
def phase(f):
    status = fixture_status(f)
    if status == "Live": return "Half-time / live"
    if status == "Finished / not active": return "Finished"
    return "Scheduled / unknown"
visible=[f for f in fixtures if status_filter=="All" or phase(f)==status_filter]
st.caption("Scores in the fixture feed may be live or final, not necessarily the halftime score.")
labels=[fixture_label(f) for f in visible]
if not visible:
    st.info("No fixtures in this filter.")
    st.stop()
with st.expander(f"Fixture list ({len(visible)})",expanded=False):
    st.dataframe(pd.DataFrame([{"Fixture":fixture_label(f),"Phase":phase(f)} for f in visible]),
                 hide_index=True, use_container_width=True, height=min(300,38*(len(visible)+1)))
selected=st.selectbox("Open a match", range(len(visible)), format_func=lambda i:labels[i])
f=visible[selected]
mid=str(f.get("id") or "")
st.subheader(f"{team_name(f,'home')} v {team_name(f,'away')}")
st.caption("Only the selected match requests detailed stats. Refresh manually to control API usage.")
@st.cache_data(ttl=90, show_spinner=False)
def fetch_stats(api_key,match_id):
    r=requests.get(f"{API_BASE}/football/matches/{match_id}/stats",
        headers={"Authorization":f"Bearer {api_key}"},timeout=25)
    r.raise_for_status()
    return r.json().get("data") or {}
@st.cache_resource(show_spinner=False)
def model_bundle():
    model_path = Path(__file__).resolve().parents[1] / "model_artifacts" / "halftime_second_half_models.joblib"
    return joblib.load(model_path)
if st.button("Fetch first-half stats",type="primary",use_container_width=True):
    fetch_stats.clear()
    st.session_state["scanner_stats_id"]=mid
    try:
        st.session_state["scanner_stats"]=fetch_stats(key,mid)
        # Streamlit widget keys persist between reruns: explicitly hydrate empty fields.
        payload=st.session_state["scanner_stats"]
        ov=payload.get("overview",{}) if isinstance(payload,dict) else {}
        for metric,name in (("expected_goals","hx"),("total_shots","shots"),("shots_on_target","sot"),("corner_kicks","corners"),("red_cards","red")):
            half=(ov.get(metric) or {}).get("first_half") or {}
            for side in ("home","away"):
                v=half.get(side) if isinstance(half,dict) else None
                widget=f"sc_{name}_{side}_{mid}" if name!="hx" else f"sc_{'hx' if side=='home' else 'ax'}_{mid}"
                if v is not None and st.session_state.get(widget) is None:
                    try:st.session_state[widget]=float(v) if name=="hx" else int(float(v))
                    except (ValueError,TypeError):pass
    except Exception as exc:
        st.session_state["scanner_stats"]={}
        st.error(f"Stats unavailable: {type(exc).__name__}. No substitute values used.")
data=st.session_state.get("scanner_stats",{}) if st.session_state.get("scanner_stats_id")==mid else {}
overview=data.get("overview",{}) if isinstance(data,dict) else {}
def half_stat(name,side):
    block=(overview.get(name) or {}).get("first_half") or {}
    value=block.get(side) if isinstance(block,dict) else None
    try: return float(value) if value is not None else None
    except (ValueError,TypeError): return None
def score_half(side):
    score=f.get("score") or {}
    # Do not treat current score as halftime score.
    for container in (score.get("half_time"),score.get("halftime"),score.get("halfTime"),f.get("half_time_score"),f.get("halfTime")):
        if isinstance(container,dict) and container.get(side) is not None:
            try:return int(container[side])
            except (ValueError,TypeError):pass
    return None
# Never use the current fixture score as a halftime score.
# A verified explicit halftime score may be supplied by the fixture feed.
for side,short in (("home","hg"),("away","ag")):
    widget=f"sc_{short}_{mid}"
    verified=score_half(side)
    if verified is not None and st.session_state.get(widget) is None:
        st.session_state[widget]=verified
if data:
    found=sum(half_stat(m,side) is not None for m in ("expected_goals","total_shots","shots_on_target","corner_kicks","red_cards") for side in ("home","away"))
    st.info(f"Stats API responded. {found}/10 first-half stat fields recognised; half-time score and pre-match odds checked separately.")
    if found==0:
        st.warning("No recognised first-half fields in this response. We must inspect its structure before claiming automatic population.")
else:
    st.info("Fetch stats when the match reaches halftime. Blank fields mean unverified data.")
with st.expander("Edit missing half-time facts",expanded=False):
    st.caption("Enter the confirmed half-time score; current live score is not used as a substitute.")
    a,b=st.columns(2)
    with a:
        hg=st.number_input("Home HT goals",0,12,value=score_half("home"),placeholder="Required",key=f"sc_hg_{mid}")
        hx=st.number_input("Home HT xG",0.0,10.0,value=half_stat("expected_goals","home"),placeholder="Required",key=f"sc_hx_{mid}")
    with b:
        ag=st.number_input("Away HT goals",0,12,value=score_half("away"),placeholder="Required",key=f"sc_ag_{mid}")
        ax=st.number_input("Away HT xG",0.0,10.0,value=half_stat("expected_goals","away"),placeholder="Required",key=f"sc_ax_{mid}")
    fields={}
    for name,metric in [("shots","total_shots"),("sot","shots_on_target"),("corners","corner_kicks"),("red","red_cards")]:
        c1,c2=st.columns(2)
        for side,col in (("home",c1),("away",c2)):
            with col:
                v=half_stat(metric,side)
                fields[(name,side)]=st.number_input(f"{side.title()} {name}",0,80,value=int(v) if v is not None else None,
                                                    placeholder="Required",key=f"sc_{name}_{side}_{mid}")
# Historical stored pre-match odds: never substitute halftime/live prices.
@st.cache_data(ttl=300,show_spinner=False)
def stored_prematch(match_id):
    import os
    from supabase import create_client
    url=os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    secret=os.environ.get("SUPABASE_SECRET_KEY") or st.secrets.get("SUPABASE_SECRET_KEY")
    if not url or not secret:return None
    db=create_client(url,secret)
    records=(db.table("historical_match_odds").select("odds_payload")
             .eq("match_id",match_id).limit(1).execute().data or [])
    if not records:return None
    payload=records[0].get("odds_payload") or {}
    bookmakers=(payload.get("data") or {}).get("bookmakers") or []
    for preferred in ("Bet365","Betfair Exchange","William Hill","Pinnacle"):
        for book in bookmakers:
            if str(book.get("bookmaker") or "").casefold()!=preferred.casefold():continue
            market=(book.get("markets") or {}).get("match_odds") or {}
            try:
                prices=[float((market.get(side) or {}).get("last_seen")) for side in ("home","draw","away")]
                if all(p>1 for p in prices):return (prices,preferred)
            except (ValueError,TypeError):pass
    return None
try:
    stored=stored_prematch(mid)
except Exception as exc:
    stored=None
    st.caption("Stored pre-match odds lookup unavailable: "+type(exc).__name__)
if stored:
    prices,source=stored
    for side,v in zip(("hp","dp","ap"),prices):
        widget=f"sc_{side}_{mid}"
        if st.session_state.get(widget) is None:st.session_state[widget]=v
    st.caption(f"Pre-match odds prefilled from stored {source} last-seen prices (not live quotes).")
st.subheader("Pre-match 1X2 odds")
st.caption("Use genuine pre-kickoff prices, not live/halftime prices. No fabricated defaults.")
c1,c2,c3=st.columns(3)
with c1:hp=st.number_input("Home",min_value=1.01,value=None,placeholder="Odds",key=f"sc_hp_{mid}")
with c2:dp=st.number_input("Draw",min_value=1.01,value=None,placeholder="Odds",key=f"sc_dp_{mid}")
with c3:ap=st.number_input("Away",min_value=1.01,value=None,placeholder="Odds",key=f"sc_ap_{mid}")
required=[hg,ag,hx,ax,hp,dp,ap,*fields.values()]
if any(v is None for v in required):
    st.warning(f"Missing {sum(v is None for v in required)} verified inputs. No fair prices calculated.")
elif fields[("sot","home")]>fields[("shots","home")] or fields[("sot","away")]>fields[("shots","away")]:
    st.error("Shots on target cannot exceed total shots.")
else:
    try:
        model=model_bundle()
        inv=np.array([1/hp,1/dp,1/ap],dtype=float)
        ph,pdraw,pa=inv/inv.sum()
        diff=hg-ag
        feat={"home_ht_goals":hg,"away_ht_goals":ag,"p_home":ph,"p_draw":pdraw,"p_away":pa,
              "ht_diff":diff,"ht_total":hg+ag,"score_strength":diff*(ph-pa),
              "h_shots":fields[("shots","home")],"a_shots":fields[("shots","away")],
              "h_sot":fields[("sot","home")],"a_sot":fields[("sot","away")],
              "h_corners":fields[("corners","home")],"a_corners":fields[("corners","away")],
              "h_red":fields[("red","home")],"a_red":fields[("red","away")],
              "home_ht_xg":hx,"away_ht_xg":ax}
        x=model["scaler"].transform(pd.DataFrame([feat])[model["feature_columns"]])
        raw={market:{str(k):float(v) for k,v in zip(clf.classes_,clf.predict_proba(x)[0])}
             for market,clf in model["models"].items()}
        # Match the original dashboard's reconciliation logic.
        o05=raw["over_0_5_2h"]["1"];o15=min(raw["over_1_5_2h"]["1"],o05)
        o25=min(raw["over_2_5_2h"]["1"],o15)
        nextp=raw["next_goal"]
        hshare=nextp["home"]/max(nextp["home"]+nextp["away"],1e-12)
        both=min(raw["both_score_2h"]["1"],raw["home_scores_2h"]["1"],raw["away_scores_2h"]["1"],o15)
        h=raw["home_scores_2h"]["1"];a=raw["away_scores_2h"]["1"]
        excess=max(0,h+a-both-o05)
        if excess:
            room_h=max(0,h-both);room_a=max(0,a-both)
            take_h=min(room_h,excess*room_h/max(room_h+room_a,1e-12))
            h-=take_h;a-=min(room_a,excess-take_h)
        result=raw["second_half_result"].copy()
        if result["draw"]<1-o05:
            factor=o05/max(result["home"]+result["away"],1e-12)
            result={"home":result["home"]*factor,"away":result["away"]*factor,"draw":1-o05}
        markets=[("Over 0.5 2H",o05),("Over 1.5 2H",o15),("Over 2.5 2H",o25),
                 ("Home scores 2H",h),("Away scores 2H",a),("Both score 2H",both),
                 ("Next goal home",o05*hshare),("Next goal away",o05*(1-hshare)),
                 ("No next goal",1-o05),("2H home win",result["home"]),
                 ("2H draw",result["draw"]),("2H away win",result["away"])]
        st.subheader("Second-half fair odds")
        st.dataframe(pd.DataFrame([{"Market":name,"Probability":f"{100*p:.1f}%","Fair odds":f"{1/p:.2f}" if p>0 else "—"}
                                  for name,p in markets]),hide_index=True,use_container_width=True)
        st.caption(f"Existing deployed model · trained through {model.get('last_training_date','unknown')} · fair odds exclude margin.")
    except Exception as exc:
        st.error(f"Pricing unavailable: {type(exc).__name__}: {str(exc)[:130]}")
st.caption("Scanner v5: exact fixture status, local model loading and expanded verified HT-score lookup; no invented odds or betting-value claims.")
