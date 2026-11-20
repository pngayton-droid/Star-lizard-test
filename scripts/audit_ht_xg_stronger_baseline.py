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
f=f.sort_values(["date","match_id"]).reset_index(drop=True)
core=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away"]
strong=core+["ht_diff","ht_total","score_strength","h_shots","a_shots","h_sot","a_sot","h_red","a_red"]
models={"M0_original":core,"M0_plus_shots_red":strong,"M1_plus_xg":strong+["home_ht_xg","away_ht_xg"]}
period=f.date.dt.to_period("M")
rows=[]
for month in sorted(period.unique()):
    tr=np.flatnonzero(period<month);te=np.flatnonzero(period==month)
    if len(tr)<1000 or len(te)<20:continue
    for model,cols in models.items():
        scale=StandardScaler().fit(f.loc[tr,cols])
        X=scale.transform(f.loc[tr,cols]);Z=scale.transform(f.loc[te,cols])
        losses=np.zeros(len(te))
        for side in ("h","a"):
            y=f["goals_"+side].to_numpy()
            reg=PoissonRegressor(alpha=10,max_iter=300).fit(X,y[tr])
            losses+=-poisson.logpmf(y[te].astype(int),np.maximum(reg.predict(Z),1e-6))
        for j,k in enumerate(te):
            rows.append({"match_id":f.at[k,"match_id"],"date":str(f.at[k,"date"].date()),"year":int(f.at[k,"date"].year),"model":model,"loss":losses[j],"red_any":int(f.at[k,"red_any"])})
p=pd.DataFrame(rows)
if p.empty:raise RuntimeError("No evaluated fixtures")
pivot=p.pivot(index=["match_id","date","year","red_any"],columns="model",values="loss").dropna()
g0=(pivot.M0_original-pivot.M0_plus_shots_red).to_numpy()
gx=(pivot.M0_plus_shots_red-pivot.M1_plus_xg).to_numpy()
meta=pivot.index.to_frame(index=False)
weeks=pd.to_datetime(meta.date).dt.to_period("W").astype(str).to_numpy()
_,wi=np.unique(weeks,return_inverse=True)
sums=np.bincount(wi,weights=gx);counts=np.bincount(wi)
rng=np.random.default_rng(20261120)
draws=rng.integers(0,len(sums),size=(3000,len(sums)))
boot=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
lo,hi=np.quantile(boot,[.025,.975])
yearly=pd.DataFrame([{"year":int(y),"fixtures":int((meta.year==y).sum()),"xg_gain":float(gx[meta.year.to_numpy()==y].mean())} for y in sorted(meta.year.unique())])
summary=pd.DataFrame([{"fixtures":len(gx),"eligible_fixtures":len(f),"gain_from_shots_red":float(g0.mean()),"xg_incremental_gain":float(gx.mean()),"xg_ci_low":float(lo),"xg_ci_high":float(hi),"positive_years":int((yearly.xg_gain>0).sum()),"years":len(yearly),"red_card_fixtures":int(meta.red_any.sum()),"xg_gain_no_red":float(gx[meta.red_any.to_numpy()==0].mean()),"odds_source_verified":False,"xg_revisions_verified":False,"note":"HT shots/red from event timeline; no pre-match totals available in this test; no betting ROI"}])
summary.to_csv("research_results/ht_xg_stronger_baseline_summary.csv",index=False)
yearly.to_csv("research_results/ht_xg_stronger_baseline_yearly.csv",index=False)
print(summary.to_string(index=False),flush=True)
