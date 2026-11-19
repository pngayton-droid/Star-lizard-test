"""Historical similarity pricing — TheStatsAPI saved records, no API calls."""
import math
from collections import defaultdict, deque
from datetime import date, timedelta
import requests
from statsapi_refresh import BASE, LEAGUES, settings
import numpy as np
import pandas as pd
import streamlit as st
from supabase import create_client

st.set_page_config(page_title="Match Matrix | Historical Pricing",page_icon="🔴",layout="wide")
st.markdown("""
<style>
:root { --united-red: #da291c; --united-gold: #fbe122; }
[data-testid="stAppViewContainer"] {
  background: linear-gradient(160deg, rgba(218,41,28,.13), transparent 340px);
}
h1, h2, h3 { letter-spacing: -.025em; }
h1 { color: #da291c !important; }
[data-testid="stMetricValue"] { color: #da291c; }
[data-testid="stMetricLabel"] { font-weight: 650; }
div[data-testid="stVerticalBlockBorderWrapper"] > div[style*="border"] {
  border-top: 2px solid rgba(218,41,28,.5);
}
div.stButton > button[kind="primary"] { background-color: #da291c; color: white; }
div[data-testid="stRadio"] label:has(input:checked) { color: #da291c; font-weight: 700; }
.united-header {
  border-left: 6px solid #fbe122; border-bottom: 3px solid #da291c;
  padding: 15px 16px; margin-bottom: 15px;
  background: linear-gradient(110deg,#8b1114,#da291c 72%,#a41918);
  color: #fff; border-radius: 10px;
}
.united-crest { float:right; width:clamp(110px,22vw,160px); height:160px; object-fit:contain; margin:0 0 4px 14px; }
.united-header::after { content:""; display:block; clear:both; }
.united-header .kicker { color: #fbe122; font-size: .8rem; font-weight: 800; letter-spacing: .14em; }
.united-header .heading { color: white; font-size: clamp(1.4rem,4vw,2.1rem); font-weight: 850; line-height: 1.2; }
.united-header .sub { color: #fff4df; font-size: .88rem; }
</style>
<div class="united-header">
 <img class="united-crest" src="https://en.wikinews.org/wiki/Special:FilePath/Manchester_United_F.C._logo.svg" alt="Manchester United club crest" loading="lazy" />
 <div class="heading">MATCH MATRIX</div>
 <div class="sub">Historical pricing lab · Goals · Corners · Cards</div>
</div>
""", unsafe_allow_html=True)
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

@st.cache_data(ttl=3600,show_spinner=False)
def match_corners_cards():
    rows=[]
    for start in range(0,100000,1000):
        batch=(client().table("historical_match_events").select("match_id,stats_data").order("match_id").range(start,start+999).execute().data or [])
        for item in batch:
            overview=((item.get("stats_data") or {}).get("overview") or {})
            rec={"match_id":item["match_id"]}
            for key,prefix in (("corner_kicks","corners"),("yellow_cards","yellows")):
                sides=((overview.get(key) or {}).get("all") or {})
                for side in ("home","away"):
                    try:rec[f"{prefix}_{side}"]=float(sides[side])
                    except (ValueError,TypeError,KeyError):rec[f"{prefix}_{side}"]=np.nan
            rows.append(rec)
        if len(batch)<1000:break
    return pd.DataFrame(rows,columns=["match_id","corners_home","corners_away","yellows_home","yellows_away"])

def season(date):
    return date.year if date.month>=7 else date.year-1

@st.cache_data(ttl=3600,show_spinner=False)
def features():
    raw=load()
    if raw.empty:return pd.DataFrame()
    raw=raw.merge(match_corners_cards(),on="match_id",how="left",validate="one_to_one")
    # Historical features computed BEFORE updating with each fixture.
    venue=defaultdict(lambda:deque(maxlen=5))
    discipline=defaultdict(lambda:deque(maxlen=5))
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
            hdisc=list(discipline[(league,season(date),h,"home")]);adisc=list(discipline[(league,season(date),a,"away")])
            def form(v,index):
                return float(np.mean([x[index] for x in v])) if len(v)>=3 else np.nan
            def ppg(s):return s[1]/s[0] if s[0] else np.nan
            def gdpg(s):return s[2]/s[0] if s[0] else np.nan
            def rank(team):
                if standings[key][team][0]<3:return np.nan
                ordered=sorted((t for t,v in standings[key].items() if v[0]>=3),key=lambda t:(standings[key][t][1],standings[key][t][2]),reverse=True)
                return ordered.index(team)+1
            out.append(dict(match_id=r.match_id,date=date,league=league,home=h,away=a,
                h_form=form(hv,0),a_form=form(av,0),h_concede=form(hv,1),a_concede=form(av,1),
                h_xg=form(hv,2),a_xg=form(av,2),h_corners_form=form(hdisc,0),a_corners_form=form(adisc,0),h_yellows_form=form(hdisc,1),a_yellows_form=form(adisc,1),h_ppg=ppg(hs),a_ppg=ppg(ass),
                h_gdpg=gdpg(hs),a_gdpg=gdpg(ass),h_rank=rank(h),a_rank=rank(a),
                ht_h=r.home_ht_goals,ht_a=r.away_ht_goals,ht_xg_h=r.home_ht_xg,ht_xg_a=r.away_ht_xg,
                hg=r.home_goals,ag=r.away_goals,corners_home=r.corners_home,corners_away=r.corners_away,yellows_home=r.yellows_home,yellows_away=r.yellows_away))
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
            if pd.notna(r.corners_home) and pd.notna(r.yellows_home):discipline[(r.competition_id,season(date),r.home_team,"home")].append((r.corners_home,r.yellows_home))
            if pd.notna(r.corners_away) and pd.notna(r.yellows_away):discipline[(r.competition_id,season(date),r.away_team,"away")].append((r.corners_away,r.yellows_away))
    return pd.DataFrame(out)

@st.cache_data(ttl=900,show_spinner=False)
def daily_fixtures(day):
    key,_,_=settings()
    if not key:
        return [],"TheStatsAPI key is not configured."
    rows=[]
    failures=[]
    with requests.Session() as session:
        session.headers.update({"Authorization":f"Bearer {key}"})
        for league,comp in LEAGUES.items():
            try:
                response=session.get(BASE+"/football/matches",params={"competition_id":comp,"date_from":day,"date_to":day,"per_page":100,"page":1},timeout=15)
                response.raise_for_status()
                payload=response.json().get("data") or []
                if isinstance(payload,dict):
                    payload=payload.get("matches") or payload.get("items") or []
                for match in payload:
                    if not isinstance(match,dict):continue
                    home=match.get("home_team") or {}
                    away=match.get("away_team") or {}
                    if not isinstance(home,dict) or not isinstance(away,dict):continue
                    kickoff=match.get("utc_date") or match.get("kickoff_utc") or ""
                    if not kickoff:continue
                    parsed=pd.to_datetime(kickoff,utc=True,errors="coerce")
                    if pd.isna(parsed) or parsed.tz_convert("Europe/London").date().isoformat()!=day:continue
                    rows.append({"date":parsed,"home":home.get("name"),"away":away.get("name"),"league":comp,"league_name":league,"status":match.get("status")})
            except (requests.RequestException,ValueError) as error:
                failures.append(league)
    return sorted(rows,key=lambda x:x["date"]),(", ".join(failures) if failures else None)

def upcoming_target(df,match):
    day=match["date"].tz_convert("Europe/London").tz_localize(None).normalize()
    league=match["league"]
    raw=load().merge(match_corners_cards(),on="match_id",how="left",validate="one_to_one")
    history=raw[(raw.competition_id==league)&(raw.match_date<day)&raw.home_goals.notna()&raw.away_goals.notna()].copy()
    h,a=match["home"],match["away"]
    season_start=pd.Timestamp(year=season(day),month=7,day=1)
    current=history[history.match_date>=season_start]
    def strength(team):
        played=current[(current.home_team==team)|(current.away_team==team)]
        pts=0;gd=0
        for x in played.itertuples(index=False):
            gf,ga=(x.home_goals,x.away_goals) if x.home_team==team else (x.away_goals,x.home_goals)
            pts+=3 if gf>ga else (1 if gf==ga else 0)
            gd+=gf-ga
        return (pts/len(played),gd/len(played)) if len(played)>=3 else (np.nan,np.nan)
    def venue(team,side):
        col="home_team" if side=="home" else "away_team"
        recent=current[current[col]==team].sort_values("match_date").tail(5)
        if len(recent)<3:return (np.nan,np.nan)
        gf="home_goals" if side=="home" else "away_goals"
        ga="away_goals" if side=="home" else "home_goals"
        return float(recent[gf].mean()),float(recent[ga].mean())
    hp,hgd=strength(h);ap,agd=strength(a)
    table={}
    for x in current.itertuples(index=False):
        for team,gf,ga in ((x.home_team,x.home_goals,x.away_goals),(x.away_team,x.away_goals,x.home_goals)):
            record=table.setdefault(team,[0,0,0,0])
            record[0]+=1
            record[1]+=3 if gf>ga else (1 if gf==ga else 0)
            record[2]+=gf-ga
            record[3]+=gf
    ordered=sorted(table,key=lambda t:(table[t][1],table[t][2],table[t][3]),reverse=True)
    def position(team):
        return ordered.index(team)+1 if team in ordered and table[team][0]>=3 else np.nan
    hf,hc=venue(h,"home");af,ac=venue(a,"away")
    def recent_stat(team,side,field):
        col="home_team" if side=="home" else "away_team"
        values=current[current[col]==team].sort_values("match_date")[field].dropna().tail(5)
        return float(values.mean()) if len(values)>=3 else np.nan
    return {"date":day,"league":league,"home":h,"away":a,"h_ppg":hp,"a_ppg":ap,"h_gdpg":hgd,"a_gdpg":agd,"h_form":hf,"a_form":af,"h_concede":hc,"a_concede":ac,"h_rank":position(h),"a_rank":position(a),"h_corners_form":recent_stat(h,"home","corners_home"),"a_corners_form":recent_stat(a,"away","corners_away"),"h_yellows_form":recent_stat(h,"home","yellows_home"),"a_yellows_form":recent_stat(a,"away","yellows_away")}

@st.cache_data(ttl=3600,show_spinner=False)
def historical_opening_prices():
    """Only true opening 1X2 quotes; no last-seen fallback."""
    output=[]
    for start in range(0,100000,1000):
        batch=(client().table("historical_match_odds").select("match_id,odds_payload").order("match_id").range(start,start+999).execute().data or [])
        for item in batch:
            payload=item.get("odds_payload") or {}
            books=(payload.get("data") or {}).get("bookmakers") or []
            candidates=[]
            for book in books:
                markets=(book.get("markets") or {}).get("match_odds") or {}
                try:
                    odds=[float((markets.get(side) or {}).get("opening")) for side in ("home","draw","away")]
                except (TypeError,ValueError):
                    continue
                if min(odds)<=1.0:continue
                margin=sum(1.0/x for x in odds)
                if not 0.95<=margin<=1.30:continue
                candidates.append([1/x/margin for x in odds])
            if candidates:
                # Median across available bookmakers, normalized again.
                probs=np.median(np.asarray(candidates),axis=0)
                probs=probs/probs.sum()
                output.append({"match_id":item["match_id"],"market_home":float(probs[0]),"market_draw":float(probs[1]),"market_away":float(probs[2])})
        if len(batch)<1000:break
    return pd.DataFrame(output,columns=["match_id","market_home","market_draw","market_away"])

def attach_opening_prices(df):
    prices=historical_opening_prices()
    return df.merge(prices,on="match_id",how="left",validate="one_to_one")

def analogues(df,target,mode,cutoff,max_distance):
    pool=df[(df.date<cutoff)&df.hg.notna()&df.ag.notna()&df.h_ppg.notna()&df.a_ppg.notna()].copy()
    if mode=="Half-time":
        pool=pool[pool.ht_h.notna()&pool.ht_a.notna()]
        pool=pool[(pool.ht_h==target["ht_h"])&(pool.ht_a==target["ht_a"])]
    fields={"h_ppg":0.55,"a_ppg":0.55,"h_gdpg":0.45,"a_gdpg":0.45,
            "h_form":0.8,"a_form":0.8,"h_concede":0.8,"a_concede":0.8}
    if mode=="Half-time":
        fields.update({"ht_xg_h":0.6,"ht_xg_a":0.6})
    if pd.notna(target.get("h_rank",np.nan)) and pd.notna(target.get("a_rank",np.nan)):
        sizes=df.groupby("league")["home"].nunique().combine(df.groupby("league")["away"].nunique(),max).clip(lower=2)
        size=float(sizes.get(target["league"],20))
        target=dict(target,rank_gap=(target["a_rank"]-target["h_rank"])/size)
        pool["rank_gap"]=(pool.a_rank-pool.h_rank)/pool.league.map(sizes)
        fields["rank_gap"]=0.20
    fields.update({"h_corners_form":2.5,"a_corners_form":2.5,"h_yellows_form":1.5,"a_yellows_form":1.5})
    odds_enabled=all(pd.notna(target.get(k,np.nan)) for k in ("market_home","market_draw","market_away"))
    if odds_enabled:
        pool=pool.dropna(subset=["market_home","market_draw","market_away"])
        fields.update({"market_home":0.12,"market_draw":0.08,"market_away":0.12})
    if len(pool)==0:return pool.assign(distance=pd.Series(dtype=float))
    score=np.zeros(len(pool))
    available=0
    for field,scale in fields.items():
        value=target.get(field,np.nan)
        if pd.isna(value):continue
        delta=(pool[field]-value).abs()/scale
        # Missing fields are penalized, not treated as a zero statistic.
        score+=delta.fillna(2.5).clip(upper=5).to_numpy()**2
        available+=1
    if available<4:return pool.iloc[:0].assign(distance=pd.Series(dtype=float))
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
    for prefix,label,lines in (("corners","corners",[7.5,8.5,9.5,10.5,11.5]),("yellows","yellow cards",[2.5,3.5,4.5,5.5])):
        totals=df[f"{prefix}_home"]+df[f"{prefix}_away"]
        valid=totals.notna()
        for line in lines:
            result[f"Over {line:g} {label}"]=(totals[valid]>line)
    return {name:(int(np.asarray(v).sum()),len(v)) for name,v in result.items()}

def score_card(matches,mode):
    n=len(matches)
    if not n:return pd.DataFrame()
    result=market_results(matches,mode)
    rows=[]
    for name,(wins,count) in result.items():
        p=wins/count if count else 0
        rows.append({"Market":name,"Wins":wins,"Matches":count,"Hit rate":f"{p:.1%}" if count else "—",
          "Historical fair odds":f"{1/p:.2f}" if p else "—",
          "Approx. 95% interval":f"{max(0,p-1.96*math.sqrt(p*(1-p)/count)):.1%}–{min(1,p+1.96*math.sqrt(p*(1-p)/count)):.1%}" if count else "—"})
    return pd.DataFrame(rows)

with st.spinner("Preparing historical features without future-data leakage…"):
    df=attach_opening_prices(features())
if df.empty:
    st.error("No historical data available.");st.stop()
st.caption(f"{len(df):,} saved fixtures · {df.date.min().date()} to {df.date.max().date()} · {df.league.nunique()} leagues")
mode=st.radio("Analysis",["Pre-match","Half-time"],horizontal=True)
source=st.radio("Fixtures",["Today's fixtures","Historical fixtures"],horizontal=True)
if source=="Today's fixtures":
    selected_day=st.date_input("Fixture date",value=date.today())
    with st.spinner("Checking scheduled kick-offs across selected leagues…"):
        schedule,error=daily_fixtures(selected_day.isoformat())
    if error:st.warning(f"Some leagues could not be loaded: {error}")
    if not schedule:
        st.info("No scheduled fixtures returned for this date. Historical fixtures remain available.")
        st.stop()
    st.caption(f"{len(schedule)} fixtures · kick-off times in UK local time · ordered earliest first")
    options=[f"{m['date'].tz_convert('Europe/London').strftime('%H:%M')} · {m['home']} v {m['away']} · {m['league_name']}" for m in schedule]
    index=st.selectbox("Select a match",range(len(schedule)),format_func=lambda i:options[i])
    target=upcoming_target(df,schedule[index])
    with st.expander("Optional bookmaker opening odds (1X2)"):
        st.caption("Enter all three opening prices to compare against historical opening prices. Leave blank for form-based matching.")
        oh=st.text_input("Home opening odds",key="oh",placeholder="e.g. 1.35")
        od=st.text_input("Draw opening odds",key="od",placeholder="e.g. 5.20")
        oa=st.text_input("Away opening odds",key="oa",placeholder="e.g. 9.00")
    if any(x.strip() for x in (oh,od,oa)):
        try:
            odds=[float(x) for x in (oh,od,oa)]
            if min(odds)<=1:raise ValueError("Prices must exceed 1")
            total=sum(1/x for x in odds)
            if not 0.95<=total<=1.30:raise ValueError("Unusual 1X2 book margin")
            target.update(dict(zip(("market_home","market_draw","market_away"),(1/x/total for x in odds))))
        except ValueError:
            st.warning("Enter three valid decimal opening prices or leave all three blank.")
            st.stop()

    if mode=="Half-time":
        st.warning("Live half-time scores and xG are not connected to this fixture list yet. Use pre-match analysis.")
        st.stop()
    if pd.isna(target["h_ppg"]) or pd.isna(target["a_ppg"]):
        st.warning("Not enough current-season results to calculate both teams' strengths.")
        st.stop()
else:
    eligible=df[(df.date>=df.date.max()-pd.Timedelta(days=365))&df.h_ppg.notna()&df.a_ppg.notna()]
    if eligible.empty:st.warning("Insufficient historical data.");st.stop()
    eligible=eligible.sort_values("date",ascending=False).head(1200)
    options={f"{r.date.date()} · {r.home} v {r.away}":i for i,r in eligible.iterrows()}
    chosen=st.selectbox("Historical fixture to price (as it stood at the time)",list(options))
    target=df.loc[options[chosen]].to_dict()
    if mode=="Half-time":
        if pd.isna(target["ht_h"]) or pd.isna(target["ht_a"]):
            st.warning("Half-time score unavailable for this fixture.");st.stop()
        st.write(f"Half-time score: **{int(target['ht_h'])}–{int(target['ht_a'])}**")
odds_mode=all(pd.notna(target.get(k,np.nan)) for k in ("market_home","market_draw","market_away"))
if odds_mode:
    st.caption("Odds-aware comparisons: historical bookmaker OPENING 1X2 prices plus pre-match form and league strength.")
else:
    st.warning("Form-and-league-strength comparisons only. No matching bookmaker opening prices supplied for this fixture; do not treat these as odds-aware prices.")
st.markdown("#### League strength before kick-off")
left,right=st.columns(2)
for column,team,rank,ppg,gd in ((left,target["home"],target.get("h_rank"),target.get("h_ppg"),target.get("h_gdpg")),(right,target["away"],target.get("a_rank"),target.get("a_ppg"),target.get("a_gdpg"))):
    with column:
        st.write(f"**{team}**")
        st.caption(f"Position: {int(rank) if pd.notna(rank) else 'N/A'}")
        st.caption(f"PPG: {ppg:.2f} · GD/game: {gd:.2f}")
st.caption("Historical standings reconstructed from saved results before kick-off. Incomplete league coverage can make positions approximate.")
# Show all bands side by side: a small close sample may still be informative.
TIERS=[(1.0,"Close"),(1.5,"Moderate"),(2.0,"Broad")]
samples={label:analogues(df,target,mode,target["date"],limit) for limit,label in TIERS}
st.subheader("Historical comparison quality")
st.caption(" · ".join(f"{label}: {len(samples[label]):,}" for _,label in TIERS))
st.caption("All bands are cumulative. Close matches are included within moderate and broad groups. Distances are exploratory, not calibrated.")
default_band=next((label for _,label in TIERS if len(samples[label])>=30),next((label for _,label in TIERS if len(samples[label])>0),"Close"))
selected=st.radio("Comparison band",["Close","Moderate","Broad"],horizontal=True,index=["Close","Moderate","Broad"].index(default_band))
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
            for market,(wins,count) in market_results(sample,mode).items():
                rate=wins/count if count else 0
                rows.append({"Market":market,"Band":label,"Games":count,"Hit rate":f"{rate:.1%}" if count else "—","Fair odds":f"{1/rate:.2f}" if wins else "—"})
        st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    with st.expander("Inspect qualifying historical fixtures"):
        st.dataframe(matches[["date","home","away","ht_h","ht_a","hg","ag","distance"]],hide_index=True,use_container_width=True)
st.warning("Strength check: this research model does not yet match historical bookmaker starting prices. Large disagreement with market favourites is a reason to investigate, not an automatic value bet.")
st.info("Fixture list comes from TheStatsAPI; comparisons use saved historical data. Live half-time pricing and bookmaker ROI are not connected. No betting edge is claimed.")
