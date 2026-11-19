"""Historical similarity pricing — TheStatsAPI saved records, no API calls."""
import math
from collections import defaultdict, deque
import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Starlizard | Similar Matches",page_icon="⚽",layout="wide")
st.title("⚽ Historical similarity pricing")
st.caption("Historical match analogues using only information known before kick-off or at half-time. No TheStatsAPI requests.")

@st.cache_resource
def client():
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_SECRET_KEY"])

@st.cache_data(ttl=3600,show_spinner=False)
def load():
    cols="match_id,match_date,competition_id,home_team,away_team,home_goals,away_goals,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_xg,away_xg"
    rows=[]
    for start in range(0,100000,1000):
        batch=(client().table("historical_xg").select(cols).order("match_date").order("match_id").range(start,start+999).execute().data or [])
        rows.extend(batch)
        if len(batch)<1000:break
    df=pd.DataFrame(rows)
    if df.empty:return df
    df["match_date"]=pd.to_datetime(df["match_date"])
    for col in ["home_goals","away_goals","home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg","home_xg","away_xg"]:
        df[col]=pd.to_numeric(df[col],errors="coerce")
    return df.sort_values(["match_date","match_id"]).reset_index(drop=True)

def season(date):
    return date.year if date.month>=7 else date.year-1

@st.cache_data(ttl=3600,show_spinner=False)
def features():
    raw=load()
    if raw.empty:return pd.DataFrame()
    # Historical features computed BEFORE updating with each fixture.
    venue=defaultdict(lambda:deque(maxlen=5))
    standings=defaultdict(lambda:defaultdict(lambda:[0,0,0]))
    out=[]
    for date,group in raw.groupby("match_date",sort=True):
        pending=[]
        for r in group.itertuples(index=False):
            league=r.competition_id
            key=(league,season(date))
            h,a=r.home_team,r.away_team
            hv=list(venue[(league,season(date),h,"home")]);av=list(venue[(league,season(date),a,"away")])
            hs=standings[key][h];ass=standings[key][a]
            def form(v,index):
                return float(np.mean([x[index] for x in v])) if len(v)>=3 else np.nan
            def ppg(s):return 3*s[1]/s[0] if s[0] else np.nan
            def gdpg(s):return s[2]/s[0] if s[0] else np.nan
            def rank(team):
                if standings[key][team][0]<3:return np.nan
                ordered=sorted((t for t,v in standings[key].items() if v[0]>=3),key=lambda t:(standings[key][t][1],standings[key][t][2]),reverse=True)
                return ordered.index(team)+1
            out.append(dict(match_id=r.match_id,date=date,league=league,home=h,away=a,
                h_form=form(hv,0),a_form=form(av,0),h_concede=form(hv,1),a_concede=form(av,1),
                h_xg=form(hv,2),a_xg=form(av,2),h_ppg=ppg(hs),a_ppg=ppg(ass),
                h_gdpg=gdpg(hs),a_gdpg=gdpg(ass),h_rank=rank(h),a_rank=rank(a),
                ht_h=r.home_ht_goals,ht_a=r.away_ht_goals,ht_xg_h=r.home_ht_xg,ht_xg_a=r.away_ht_xg,
                hg=r.home_goals,ag=r.away_goals))
            pending.append(r)
        # No same-day result can enter another same-day pre-match feature.
        for r in pending:
            if pd.isna(r.home_goals) or pd.isna(r.away_goals):continue
            key=(r.competition_id,season(date))
            hg,ag=float(r.home_goals),float(r.away_goals)
            for team,gf,ga in [(r.home_team,hg,ag),(r.away_team,ag,hg)]:
                v=standings[key][team];v[0]+=1;v[1]+=3 if gf>ga else (1 if gf==ga else 0);v[2]+=gf-ga
            venue[(r.competition_id,season(date),r.home_team,"home")].append((hg,ag,r.home_xg if pd.notna(r.home_xg) else hg))
            venue[(r.competition_id,season(date),r.away_team,"away")].append((ag,hg,r.away_xg if pd.notna(r.away_xg) else ag))
    return pd.DataFrame(out)

def analogues(df,target,mode,cutoff,max_distance):
    pool=df[(df.date<cutoff)&df.hg.notna()&df.ag.notna()&df.h_ppg.notna()&df.a_ppg.notna()].copy()
    if mode=="Half-time":
        pool=pool[pool.ht_h.notna()&pool.ht_a.notna()]
        pool=pool[(pool.ht_h==target["ht_h"])&(pool.ht_a==target["ht_a"])]
    fields={"h_ppg":0.65,"a_ppg":0.65,"h_gdpg":0.5,"a_gdpg":0.5,
            "h_form":0.8,"a_form":0.8,"h_concede":0.8,"a_concede":0.8}
    if mode=="Half-time":
        fields.update({"ht_xg_h":0.6,"ht_xg_a":0.6})
    if len(pool)==0:return pool
    score=np.zeros(len(pool))
    available=0
    for field,scale in fields.items():
        value=target.get(field,np.nan)
        if pd.isna(value):continue
        delta=(pool[field]-value).abs()/scale
        # Missing fields are penalized, not treated as a zero statistic.
        score+=delta.fillna(2.5).clip(upper=5).to_numpy()**2
        available+=1
    if available<4:return pool.iloc[:0]
    # Same competition preferred but never a mandatory filter.
    score+=np.where(pool.league==target["league"],0,0.5)
    pool["distance"]=np.sqrt(score/available)
    # Quality gate: do not force a fixed number of weak analogues.
    return pool.loc[pool["distance"]<=max_distance].sort_values("distance")

def market_results(df,mode):
    h=df.hg.to_numpy();a=df.ag.to_numpy()
    result={"Home win":h>a,"Draw":h==a,"Away win":h<a,
            "Over 1.5 goals":h+a>=2,"Over 2.5 goals":h+a>=3,
            "Over 3.5 goals":h+a>=4,"BTTS Yes":(h>0)&(a>0)}
    if mode=="Half-time":
        hh=df.ht_h.to_numpy();aa=df.ht_a.to_numpy()
        result={"Home wins from HT":h>a,"Draw from HT":h==a,"Away wins from HT":h<a,
                "Over 0.5 second-half goals":h+a-hh-aa>=1,
                "Over 1.5 second-half goals":h+a-hh-aa>=2,
                "Over 2.5 second-half goals":h+a-hh-aa>=3,
                "Home scores in second half":h>hh,"Away scores in second half":a>aa}
    return {name:float(np.mean(v)) for name,v in result.items()}

def score_card(matches,mode):
    n=len(matches)
    if not n:return pd.DataFrame()
    result=market_results(matches,mode)
    return pd.DataFrame([{"Market":name,"Wins":round(p*n),"Matches":n,"Hit rate":f"{p:.1%}",
       "Historical fair odds":f"{1/p:.2f}" if p else "—",
       "Approx. 95% interval":f"{max(0,p-1.96*math.sqrt(p*(1-p)/n)):.1%}–{min(1,p+1.96*math.sqrt(p*(1-p)/n)):.1%}"} for name,p in result.items()])

with st.spinner("Preparing historical features without future-data leakage…"):
    df=features()
if df.empty:
    st.error("No historical data available.");st.stop()
st.caption(f"{len(df):,} saved fixtures · {df.date.min().date()} to {df.date.max().date()} · {df.league.nunique()} leagues")
mode=st.radio("Analysis",["Pre-match","Half-time"],horizontal=True)
# Pick a historical fixture to enable a genuine point-in-time comparison.
eligible=df[(df.date>=df.date.max()-pd.Timedelta(days=365))&df.h_ppg.notna()&df.a_ppg.notna()]
if eligible.empty:st.warning("Insufficient prior-season data.");st.stop()
eligible=eligible.sort_values("date",ascending=False).head(1200)
options={f"{r.date.date()} · {r.home} v {r.away}":i for i,r in eligible.iterrows()}
chosen=st.selectbox("Historical fixture to price (as it stood at the time)",list(options))
target=df.loc[options[chosen]].to_dict()
if mode=="Half-time":
    if pd.isna(target["ht_h"]) or pd.isna(target["ht_a"]):
        st.warning("Half-time score unavailable for this fixture.");st.stop()
    st.write(f"Half-time score: **{int(target['ht_h'])}–{int(target['ht_a'])}**")
# Show all bands side by side: a small close sample may still be informative.
TIERS=[(1.0,"Close"),(1.5,"Moderate"),(2.0,"Broad")]
samples={label:analogues(df,target,mode,target["date"],limit) for limit,label in TIERS}
st.subheader("Historical comparison quality")
st.caption(" · ".join(f"{label}: {len(samples[label]):,}" for _,label in TIERS))
st.caption("All bands are cumulative. Close matches are included within moderate and broad groups.")
selected=st.radio("Comparison band",["Close","Moderate","Broad"],horizontal=True,index=0)
matches=samples[selected]
st.write(f"**{len(matches):,} qualifying matches** in the {selected.lower()} band")
if len(matches)<30:
    st.warning("Small sample: prices below are exploratory and highly uncertain. Compare other bands before drawing conclusions.")
if len(matches)==0:
    st.info("No historical comparisons in this band.")
else:
    prices=score_card(matches,mode)
    for item in prices.to_dict("records"):
        with st.container(border=True):
            st.markdown(f"**{item['Market']}**")
            a,b,d=st.columns(3)
            a.metric("Fair odds",item["Historical fair odds"])
            b.metric("Hit rate",item["Hit rate"])
            d.metric("Wins / games",f"{item['Wins']}/{item['Matches']}")
            st.caption(f"Approximate 95% interval: {item['Approx. 95% interval']}")
    with st.expander("Compare all three similarity bands"):
        rows=[]
        for _,label in TIERS:
            sample=samples[label]
            if len(sample)==0:continue
            for market,rate in market_results(sample,mode).items():
                rows.append({"Market":market,"Band":label,"Games":len(sample),"Hit rate":f"{rate:.1%}","Fair odds":f"{1/rate:.2f}" if rate else "—"})
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    with st.expander("Inspect qualifying historical fixtures"):
        st.dataframe(matches[["date","home","away","ht_h","ht_a","hg","ag","distance"]],hide_index=True,use_container_width=True)
st.warning("Strength check: this research model does not yet match historical bookmaker starting prices. Large disagreement with market favourites is a reason to investigate, not an automatic value bet.")
st.info("This is a historical point-in-time research page. Current upcoming-fixture predictions and live halftime odds are not yet connected. No bookmaker ROI is claimed.")
