"""Manual empirical football pricing from saved StatsAPI match results.

Read-only. No API calls. Historical frequencies are descriptive estimates, not
a bookmaker-grade predictive model. Small samples must be treated cautiously.
"""
import math
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Starlizard | Manual Fair Odds",page_icon="⚽",layout="wide")
st.title("⚽ Starlizard — Manual Fair Odds")
st.caption("Enter teams and match state. All calculations use our saved historical data, not live API requests.")

@st.cache_resource
def db():
    return create_client(st.secrets["SUPABASE_URL"],st.secrets["SUPABASE_SECRET_KEY"])

FIELDS="match_id,match_date,competition_id,home_team,away_team,home_goals,away_goals,home_ht_goals,away_ht_goals"
@st.cache_data(ttl=1800,show_spinner=False)
def load_team(team,venue):
    col="home_team" if venue=="home" else "away_team"
    result=[]
    # Query only a single team; page in bounded batches.
    for offset in range(0,1000,500):
        batch=(db().table("historical_xg").select(FIELDS).eq(col,team)
               .not_.is_("home_goals","null").not_.is_("away_goals","null")
               .not_.is_("home_ht_goals","null").not_.is_("away_ht_goals","null")
               .order("match_date",desc=True).range(offset,offset+499).execute().data or [])
        result.extend(batch)
        if len(batch)<500:break
    return result

@st.cache_data(ttl=1800,show_spinner=False)
def team_names():
    # Fetch compact names only; pagination avoids PostgREST's 1k default.
    names=set()
    for offset in range(0,25000,1000):
        rows=(db().table("historical_xg").select("home_team,away_team")
              .order("match_id").range(offset,offset+999).execute().data or [])
        for row in rows:
            if row.get("home_team"):names.add(row["home_team"])
            if row.get("away_team"):names.add(row["away_team"])
        if len(rows)<1000:break
    return sorted(names)

def transformed(rows,side):
    out=[]
    for r in rows:
        try:
            h,a,hh,ah=[int(r[k]) for k in ("home_goals","away_goals","home_ht_goals","away_ht_goals")]
            if min(h,a,hh,ah)<0 or h<hh or a<ah:continue
            if side=="home": gf,ga,hf,ha=h,a,hh,ah
            else:gf,ga,hf,ha=a,h,ah,hh
            out.append({"date":r["match_date"],"match_id":r["match_id"],"gf":gf,"ga":ga,"hf":hf,"ha":ha,
                        "sf":gf-hf,"sa":ga-ha,"league":r["competition_id"]})
        except (ValueError,TypeError,KeyError):continue
    return out

def odds(p):
    return f"{1/p:.2f}" if p>0 else "—"

def market_table(matches,stage,hh=0,ah=0):
    n=len(matches)
    if not n:return pd.DataFrame()
    items=[]
    def add(label,fn):
        k=sum(bool(fn(r)) for r in matches)
        p=k/n
        items.append({"Outcome":label,"Occurred":k,"Matches":n,"Frequency":f"{p:.1%}","Fair decimal odds":odds(p)})
    if stage=="Pre-match":
        add("Home win",lambda r:r["h"]>r["a"])
        add("Draw",lambda r:r["h"]==r["a"])
        add("Away win",lambda r:r["h"]<r["a"])
        add("Over 1.5 goals",lambda r:r["h"]+r["a"]>=2)
        add("Over 2.5 goals",lambda r:r["h"]+r["a"]>=3)
        add("Over 3.5 goals",lambda r:r["h"]+r["a"]>=4)
        add("Both teams score",lambda r:r["h"]>0 and r["a"]>0)
        add("0–0 at half-time",lambda r:r["hh"]==0 and r["ah"]==0)
        add("Home wins both halves",lambda r:r["hh"]>r["ah"] and r["sh"]>r["sa"])
        add("Away wins both halves",lambda r:r["hh"]<r["ah"] and r["sh"]<r["sa"])
    else:
        add("Home wins full-time",lambda r:r["h"]>r["a"])
        add("Full-time draw",lambda r:r["h"]==r["a"])
        add("Away wins full-time",lambda r:r["h"]<r["a"])
        add("Home wins second half",lambda r:r["sh"]>r["sa"])
        add("Second half drawn",lambda r:r["sh"]==r["sa"])
        add("Away wins second half",lambda r:r["sh"]<r["sa"])
        add("Over 0.5 second-half goals",lambda r:r["sh"]+r["sa"]>=1)
        add("Over 1.5 second-half goals",lambda r:r["sh"]+r["sa"]>=2)
        add("Over 2.5 second-half goals",lambda r:r["sh"]+r["sa"]>=3)
        add("Home scores in second half",lambda r:r["sh"]>=1)
        add("Away scores in second half",lambda r:r["sa"]>=1)
        add("Both teams score in second half",lambda r:r["sh"]>=1 and r["sa"]>=1)
    return pd.DataFrame(items)

def score_table(matches,half=False):
    n=len(matches)
    if not n:return pd.DataFrame()
    counts={}
    for r in matches:
        score=f'{r["hh"]}–{r["ah"]}' if half else f'{r["h"]}–{r["a"]}'
        counts[score]=counts.get(score,0)+1
    return pd.DataFrame([{"Score":s,"Occurred":k,"Matches":n,"Frequency":f"{k/n:.1%}","Fair decimal odds":odds(k/n)}
                         for s,k in sorted(counts.items(),key=lambda item:(-item[1],item[0]))[:15]])

try:
    names=team_names()
except Exception as exc:
    st.error(f"Could not read the saved database: {exc}")
    st.stop()
if len(names)<2:
    st.warning("No historical teams available.")
    st.stop()
mode=st.radio("Pricing mode",["Pre-match","Half-time"],horizontal=True)
c1,c2=st.columns(2)
with c1:
    home=st.selectbox("Home team",names,index=names.index("Manchester United") if "Manchester United" in names else 0)
with c2:
    away=st.selectbox("Away team",names,index=names.index("Aston Villa") if "Aston Villa" in names else min(1,len(names)-1))
sample=st.select_slider("Recent matches per team at the relevant venue",options=[5,10,15,20,30,50,100],value=30)
hh=ah=0
if mode=="Half-time":
    c1,c2=st.columns(2)
    with c1:hh=st.number_input("Home goals at half-time",min_value=0,max_value=10,value=0)
    with c2:ah=st.number_input("Away goals at half-time",min_value=0,max_value=10,value=0)
if home==away:
    st.error("Choose two different teams.")
    st.stop()
if st.button("Calculate historical fair odds",type="primary",use_container_width=True):
    with st.spinner("Reading saved match history…"):
        try:
            home_rows=transformed(load_team(home,"home"),"home")[:sample]
            away_rows=transformed(load_team(away,"away"),"away")[:sample]
        except Exception as exc:
            st.error(f"Database query failed: {exc}")
            st.stop()
    # Construct two independent, explicitly labelled perspectives.
    # Home team: actual home scorelines. Away team: actual away scorelines,
    # remapped so selected away team's goals are always the away side.
    combined=[]
    for r in home_rows:
        combined.append({"h":r["gf"],"a":r["ga"],"hh":r["hf"],"ah":r["ha"],"sh":r["sf"],"sa":r["sa"],"source":f"{home} home","date":r["date"]})
    for r in away_rows:
        combined.append({"h":r["ga"],"a":r["gf"],"hh":r["ha"],"ah":r["hf"],"sh":r["sa"],"sa":r["sf"],"source":f"{away} away","date":r["date"]})
    st.info(f"Sample: {len(home_rows)} {home} home matches + {len(away_rows)} {away} away matches. "
            "These are pooled historical observations, not previous head-to-head fixtures or a calibrated match forecast.")
    if mode=="Half-time":
        filtered=[r for r in combined if r["hh"]==hh and r["ah"]==ah]
        st.metric("Matching historical half-time states",len(filtered))
        st.caption(f"Only matches at half-time {hh}–{ah} are used below. Results are conditional on the exact half-time score.")
    else:
        filtered=combined
        st.metric("Historical observations",len(filtered))
    if len(filtered)<10:
        st.warning("Fewer than 10 comparable observations. Fair odds would be highly unreliable; increase the sample or change the match state.")
    if not filtered:
        st.stop()
    st.subheader("Historical outcomes and implied fair odds")
    st.dataframe(market_table(filtered,mode,hh,ah),hide_index=True,use_container_width=True)
    st.subheader("Most frequent scorelines")
    st.dataframe(score_table(filtered,half=False),hide_index=True,use_container_width=True)
    if mode=="Pre-match":
        st.subheader("Most frequent half-time scores")
        st.dataframe(score_table(filtered,half=True),hide_index=True,use_container_width=True)
    st.caption("Fair odds = 1 ÷ observed frequency, without bookmaker margin. They are descriptive, not necessarily accurate probabilities for today's match. "
               "No opponent-strength adjustment, bookmaker-price adjustment, or live information is applied. "
               "Repeated historical team appearances can overlap; never treat the sample as independent evidence of a betting edge.")
