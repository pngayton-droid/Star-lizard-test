"""Chronological 1X2 Matrix audit across ALL selections, with odds bands and volume.
Train each calibration exclusively on preceding seasons. One highest-EV pick per match.
No bookmaker blending, market-derived calibration, or retrospective threshold tuning.
"""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
f=pd.read_csv("research_results/matrix_draw_full_history_forecasts.csv")
cols=[f"raw_{i}" for i in range(3)]
pcols=[f"price_{i}" for i in range(3)]
out=[]
for year in sorted(f.year.unique()):
 if year<2022:continue
 train=f[(f.year>=2021)&(f.year<year)]
 test=f[f.year==year]
 if len(train)<250 or len(test)<50:continue
 model=LogisticRegression(C=.05,max_iter=1000)
 model.fit(np.log(np.clip(train[cols].to_numpy(float),.005,1)),train.actual.to_numpy(int))
 raw=test[cols].to_numpy(float)
 cal=model.predict_proba(np.log(np.clip(raw,.005,1)))
 prices=test[pcols].to_numpy(float)
 actual=test.actual.to_numpy(int)
 inv=1/prices;book=inv/inv.sum(axis=1,keepdims=True)
 for method,probs in (("raw",raw),("calibrated",cal),("bookmaker_no_vig",book)):
  brier=float(np.mean(np.sum((probs-np.eye(3)[actual])**2,axis=1)/3))
  if method=="bookmaker_no_vig":
   out.append(dict(year=int(year),method=method,selection="forecast_only",odds_band="all",threshold=.05,fixtures=len(test),bets=0,units=0,roi=np.nan,brier=brier,mean_odds=np.nan,mean_ev=np.nan))
   continue
  ev=probs*prices-1
  fav=np.where(prices[:,0]<=prices[:,2],0,2)
  dog=2-fav
  groups={"all_1x2":np.ones_like(ev,bool),"favourite_only":np.arange(3)[None,:]==fav[:,None],"draw_only":np.arange(3)[None,:]==1,"underdog_only":np.arange(3)[None,:]==dog[:,None],"favourite_or_draw":(np.arange(3)[None,:]==fav[:,None])|(np.arange(3)[None,:]==1)}
  for selection,mask in groups.items():
   masked=np.where(mask,ev,-np.inf)
   chosen=masked.argmax(axis=1)
   best=masked[np.arange(len(test)),chosen]
   chosen_odds=prices[np.arange(len(test)),chosen]
   for threshold in (.05,.15):
    selected=best>=threshold
    for label,odds_mask in {"all":np.ones(len(test),bool),"1.20-1.99":(chosen_odds>=1.2)&(chosen_odds<2),"2.00-2.99":(chosen_odds>=2)&(chosen_odds<3),"3.00-3.99":(chosen_odds>=3)&(chosen_odds<4),"4.00-5.99":(chosen_odds>=4)&(chosen_odds<6),"6.00-20.00":(chosen_odds>=6)&(chosen_odds<=20)}.items():
     idx=np.flatnonzero(selected&odds_mask)
     returns=np.where(actual[idx]==chosen[idx],chosen_odds[idx]-1,-1)
     out.append(dict(year=int(year),method=method,selection=selection,odds_band=label,threshold=threshold,fixtures=len(test),bets=len(idx),units=float(returns.sum()),roi=float(returns.mean()) if len(idx) else np.nan,brier=brier,mean_odds=float(chosen_odds[idx].mean()) if len(idx) else np.nan,mean_ev=float(best[idx].mean()) if len(idx) else np.nan))
r=pd.DataFrame(out)
s=r[(r.odds_band=="all")&(r.selection!="forecast_only")].groupby(["method","selection","threshold"],as_index=False).agg(bets=("bets","sum"),units=("units","sum"))
s["roi"]=s.units/s.bets.replace(0,np.nan)
os.makedirs("research_results",exist_ok=True)
r.to_csv("research_results/matrix_1x2_walkforward_by_year.csv",index=False)
s.to_csv("research_results/matrix_1x2_walkforward_summary.csv",index=False)
print(s.to_string(index=False),flush=True)
print(r[(r.method=="calibrated")&(r.selection=="all_1x2")&(r.threshold==.05)].to_string(index=False),flush=True)
