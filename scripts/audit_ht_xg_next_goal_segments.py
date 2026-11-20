"""Compare HT xG with an enhanced pre-HT baseline. Strictly walk-forward.
No live prices, no ROI claims. Missing timelines excluded from paired comparison.
"""
import os
import time
import numpy as np
import pandas as pd
from supabase import create_client
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import PoissonRegressor
from scipy.stats import poisson

db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
os.makedirs("research_results",exist_ok=True)
def fetch(table,cols):
    out=[]
    batch_size=50 if table=="historical_match_events" else 1000
    start=0
    while start<100000:
        for attempt in range(4):
            try:
                chunk=db.table(table).select(cols).range(start,start+batch_size-1).execute().data or []
                break
            except Exception as exc:
                if "57014" not in str(exc) or attempt==3:raise
                print(f"Timeout on {table} at {start}, retry {attempt+1}",flush=True)
                time.sleep(2*(attempt+1))
        out.extend(chunk)
        start+=batch_size
        if len(chunk)<batch_size:break
    print(f"Fetched {table}: {len(out)} rows",flush=True)
    return pd.DataFrame(out)

h=fetch("halftime_research_outcomes","competition_id,match_date,home_team,away_team,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_goals,away_goals")
b=fetch("starlizard_backtest_1x2","match_date,home_team,away_team,home_price,draw_price,away_price")
x=fetch("historical_xg","match_id,match_date,home_team,away_team")
ev=fetch("historical_match_events","match_id,timeline_data")
# Only actual StatsAPI IDs have event timelines; synthetic legacy rows duplicate fixtures.
x=x[x.match_id.astype(str).str.startswith("mt_")].copy()
key=["match_date","home_team","away_team"]
for label,df in [("HT",h),("odds",b),("match ids",x)]:
    if df.duplicated(key).any():raise RuntimeError("Duplicate keys in "+label)
f=h.merge(b,on=key,validate="one_to_one").merge(x,on=key,validate="one_to_one")
if ev.match_id.duplicated().any():raise RuntimeError("Duplicate timeline match ids")
f=f.merge(ev,on="match_id",how="left",validate="one_to_one")
# Build by row, respecting actual home/away team names.
def features(r):
    data=r.timeline_data if isinstance(r.timeline_data,dict) else {}
    events=data.get("events")
    if not isinstance(events,list):return None
    z={k:0 for k in ["h_shots","a_shots","h_sot","a_sot","h_red","a_red"]}
    for e in events:
        if not isinstance(e,dict) or e.get("period")!="first_half":continue
        team=e.get("team") or {}
        name=team.get("name") if isinstance(team,dict) else None
        side="h" if name==r.home_team else "a" if name==r.away_team else None
        if not side:continue
        typ=e.get("type")
        if typ in ("shot_on_target","shot_off_target","shot_blocked","shot_woodwork"):z[side+"_shots"]+=1
        if typ=="shot_on_target":z[side+"_sot"]+=1
        if typ in ("red_card","yellow_red_card","second_yellow_card"):z[side+"_red"]+=1
    goals=[]
    for e in events:
        if not isinstance(e,dict) or e.get("period")!="second_half" or e.get("type") not in ("goal","penalty_scored","own_goal"):continue
        team=e.get("team") or {}
        name=team.get("name") if isinstance(team,dict) else None
        if name not in (r.home_team,r.away_team):continue
        side="h" if name==r.home_team else "a"
        if e.get("type")=="own_goal":side="a" if side=="h" else "h"
        goals.append((int(e.get("minute") or 0),int(e.get("extra_time") or 0),int(e.get("sequence") or 0),side))
    goals.sort()
    z["first_2h"]=goals[0][3] if goals else "none"
    z["timeline_goals"]=len(goals)
    return z
# Timeline-derived features are available at HT; unverified event-name matches are not imputed.
derived=[features(r) for r in f.itertuples(index=False)]
valid=[i for i,z in enumerate(derived) if z is not None]
f=f.iloc[valid].copy().reset_index(drop=True)
d=pd.DataFrame([derived[i] for i in valid])
f=pd.concat([f.drop(columns=["timeline_data"]),d],axis=1)
num=["home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg","home_goals","away_goals","home_price","draw_price","away_price"]
for c in num:f[c]=pd.to_numeric(f[c],errors="coerce")
f=f.dropna(subset=num)
f=f[(f[["home_price","draw_price","away_price"]]>1).all(axis=1)]
f=f[(f.home_goals>=f.home_ht_goals)&(f.away_goals>=f.away_ht_goals)].copy()
f["date"]=pd.to_datetime(f.match_date)
f["goals_h"]=f.home_goals-f.home_ht_goals
f["goals_a"]=f.away_goals-f.away_ht_goals
inv=1/f[["home_price","draw_price","away_price"]].to_numpy(float)
m=inv/inv.sum(axis=1,keepdims=True)
for i,k in enumerate(["p_home","p_draw","p_away"]):f[k]=m[:,i]
f["ht_diff"]=f.home_ht_goals-f.away_ht_goals
f["ht_total"]=f.home_ht_goals+f.away_ht_goals
f["score_strength"]=f.ht_diff*(f.p_home-f.p_away)
f["red_any"]=((f.h_red+f.a_red)>0).astype(int)
f=f[f.timeline_goals==(f.goals_h+f.goals_a)].copy()
f=f.sort_values(["date","match_id"]).reset_index(drop=True)
core=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away"]
strong=core+["ht_diff","ht_total","score_strength","h_shots","a_shots","h_sot","a_sot","h_red","a_red"]
models={"strong":strong,"plus_xg":strong+["home_ht_xg","away_ht_xg"]}
period=f.date.dt.to_period("M")
rows=[]
for month in sorted(period.unique()):
    tr=np.flatnonzero(period<month);te=np.flatnonzero(period==month)
    if len(tr)<1000 or len(te)<20:continue
    for model,cols in models.items():
        scale=StandardScaler().fit(f.loc[tr,cols])
        X=scale.transform(f.loc[tr,cols]);Z=scale.transform(f.loc[te,cols])
        rates={}
        for side in ("h","a"):
            y=f["goals_"+side].to_numpy()
            reg=PoissonRegressor(alpha=10,max_iter=300).fit(X,y[tr])
            rates[side]=np.maximum(reg.predict(Z),1e-9)
        lh,la=rates["h"],rates["a"]
        total=lh+la
        for j,k in enumerate(te):
            r=f.iloc[k]
            for threshold in (1,2,3):
                prob=float(poisson.sf(threshold-1,total[j]))
                rows.append((r.match_id,str(r.date.date()),int(r.date.year),model,"over_"+str(threshold-0.5),prob,int(r.goals_h+r.goals_a>=threshold)))
            probs={"none":float(np.exp(-total[j])),"h":float(-np.expm1(-total[j])*lh[j]/total[j]),"a":float(-np.expm1(-total[j])*la[j]/total[j])}
            for outcome,prob in probs.items():
                rows.append((r.match_id,str(r.date.date()),int(r.date.year),model,"next_"+outcome,prob,int(r.first_2h==outcome)))
p=pd.DataFrame(rows,columns=["match_id","date","year","model","market","prob","actual"])
if p.empty:raise RuntimeError("No evaluated fixtures")
# Segments are defined entirely from information available at halftime.
f["trailing_side"]=np.where(f.ht_diff<0,"h",np.where(f.ht_diff>0,"a","none"))
f["trailing_margin"]=f.ht_diff.abs()
f["favorite_side"]=np.where(f.p_home>f.p_away,"h","a")
f["favorite_trailing"]=(f.trailing_side==f.favorite_side)&(f.trailing_side!="none")
f["trailing_xg"]=np.where(f.trailing_side=="h",f.home_ht_xg,f.away_ht_xg)
f["leading_xg"]=np.where(f.trailing_side=="h",f.away_ht_xg,f.home_ht_xg)
f["trailing_dominates_xg"]=(f.trailing_side!="none")&(f.trailing_xg>f.leading_xg)
f["trailing_next_market"]=np.where(f.trailing_side=="h","next_h","next_a")
f["favorite_next_market"]=np.where(f.favorite_side=="h","next_h","next_a")
segments=f[["match_id","trailing_side","trailing_margin","favorite_trailing","trailing_dominates_xg","trailing_xg","trailing_next_market","favorite_next_market","red_any"]]
p=p.merge(segments,on="match_id",how="left",validate="many_to_one")
p["prob"]=p.prob.clip(1e-9,1-1e-9)
p["brier"]=(p.prob-p.actual)**2
p["logloss"]=-(p.actual*np.log(p.prob)+(1-p.actual)*np.log1p(-p.prob))
index=["match_id","date","year","market"]
paired=p.pivot(index=index,columns="model",values=["brier","logloss","prob","actual"]).dropna()
meta=paired.index.to_frame(index=False)
meta=meta.merge(segments,on="match_id",how="left",validate="many_to_one")
gain=(paired[("logloss","strong")]-paired[("logloss","plus_xg")]).to_numpy()
meta["gain"]=gain
meta["actual"]=paired[("actual","strong")].to_numpy()
meta["pred_xg"]=paired[("prob","plus_xg")].to_numpy()
meta["pred_base"]=paired[("prob","strong")].to_numpy()
conditions={
 "all_next_team":(meta.market.isin(["next_h","next_a"])),
 "trailing_by_1_next":(meta.trailing_margin==1)&(meta.market==meta.trailing_next_market),
 "trailing_by_2plus_next":(meta.trailing_margin>=2)&(meta.market==meta.trailing_next_market),
 "favorite_trailing_next":meta.favorite_trailing&(meta.market==meta.favorite_next_market),
 "favorite_trailing_by_1_next":meta.favorite_trailing&(meta.trailing_margin==1)&(meta.market==meta.favorite_next_market),
 "trailing_xg_lead_next":meta.trailing_dominates_xg&(meta.market==meta.trailing_next_market),
 "trailing_xg_ge_020_next":(meta.trailing_side!="none")&(meta.trailing_xg>=0.20)&(meta.market==meta.trailing_next_market),
 "trailing_xg_lead_by_1_next":meta.trailing_dominates_xg&(meta.trailing_margin==1)&(meta.market==meta.trailing_next_market),
 "favorite_trailing_xg_lead_next":meta.favorite_trailing&meta.trailing_dominates_xg&(meta.market==meta.trailing_next_market),
 "no_red_trailing_next":(meta.red_any==0)&(meta.trailing_side!="none")&(meta.market==meta.trailing_next_market),
}
out=[]
for name,mask in conditions.items():
    sub=meta[mask].copy()
    if len(sub)<30:continue
    weekly=sub.groupby(pd.to_datetime(sub.date).dt.to_period("W")).agg(gain_sum=("gain","sum"),n=("gain","size"))
    rng=np.random.default_rng(20261120)
    draws=rng.integers(0,len(weekly),size=(2000,len(weekly)))
    sums=weekly.gain_sum.to_numpy();counts=weekly.n.to_numpy()
    boots=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
    lo,hi=np.quantile(boots,[.025,.975])
    yr=sub.groupby("year").gain.mean()
    out.append(dict(segment=name,fixtures=len(sub),xg_logloss_gain=float(sub.gain.mean()),ci_low=float(lo),ci_high=float(hi),positive_years=int((yr>0).sum()),years=len(yr),gain_2026=float(yr.get(2026,float("nan"))),actual_hit_rate=float(sub.actual.mean()),mean_model_probability=float(sub.pred_xg.mean()),mean_baseline_probability=float(sub.pred_base.mean())))
pd.DataFrame(out).to_csv("research_results/ht_xg_next_goal_segments.csv",index=False)
print(pd.DataFrame(out).to_string(index=False),flush=True)
print("All rates are observed frequencies, NOT betting ROI.",flush=True)
