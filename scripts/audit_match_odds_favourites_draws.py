"""Selection restriction audit on previously frozen 1X2 Matrix forecasts."""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
f=pd.read_csv("research_results/match_odds_calibration_forecasts.csv")
train=f[f.year<=2024]
cal=LogisticRegression(C=0.05,max_iter=1000)
cols=[f"raw_{i}" for i in range(3)]
cal.fit(np.log(np.clip(train[cols].to_numpy(float),.005,1)),train.actual.to_numpy(int))
out=[]
for year in (2025,2026):
 d=f[f.year==year].copy()
 odds=d[[f"price_{i}" for i in range(3)]].to_numpy(float)
 actual=d.actual.to_numpy(int)
 favorite=np.where(odds[:,0]<=odds[:,2],0,2)
 underdog=2-favorite
 raw=d[cols].to_numpy(float)
 preds={"raw":raw,"calibrated":cal.predict_proba(np.log(np.clip(raw,.005,1)))}
 for model,p in preds.items():
  ev=p*odds-1
  for selection in ("unrestricted","favourite_only","favourite_or_draw","draw_only","underdog_only"):
   mask=np.ones_like(ev,dtype=bool)
   if selection!="unrestricted":
    mask[:]=False
    if selection in ("favourite_only","favourite_or_draw"):mask[np.arange(len(d)),favorite]=True
    if selection in ("draw_only","favourite_or_draw"):mask[:,1]=True
    if selection=="underdog_only":mask[np.arange(len(d)),underdog]=True
   eligible=np.where(mask,ev,-np.inf)
   chosen=eligible.argmax(axis=1)
   best=eligible[np.arange(len(d)),chosen]
   for threshold in (.05,.15,.30):
    pick=best>=threshold
    idx=np.flatnonzero(pick)
    returns=np.where(actual[idx]==chosen[idx],odds[idx,chosen[idx]]-1,-1)
    out.append(dict(year=year,model=model,selection=selection,threshold=threshold,fixtures=len(d),bets=len(idx),roi=float(returns.mean()) if len(idx) else np.nan,units=float(returns.sum()),predicted_roi=float(best[idx].mean()) if len(idx) else np.nan,mean_odds=float(odds[idx,chosen[idx]].mean()) if len(idx) else np.nan))
res=pd.DataFrame(out)
combined=res.groupby(["model","selection","threshold"],as_index=False).agg(fixtures=("fixtures","sum"),bets=("bets","sum"),units=("units","sum"))
combined["roi"]=combined.units/combined.bets.replace(0,np.nan)
os.makedirs("research_results",exist_ok=True)
res.to_csv("research_results/match_odds_favourites_draws_by_year.csv",index=False)
combined.to_csv("research_results/match_odds_favourites_draws_summary.csv",index=False)
print(combined[combined.threshold==.05].to_string(index=False),flush=True)
