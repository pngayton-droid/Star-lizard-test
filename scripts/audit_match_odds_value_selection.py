"""Diagnose value-selection bias using frozen chronological Matrix forecasts."""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
path="research_results/match_odds_calibration_forecasts.csv"
df=pd.read_csv(path)
assert len(df)>10000 and df.match_id.is_unique
train=df[df.year<=2024].copy()
valid=df[df.year>=2025].copy()
def mat(f,p):return f[[f"{p}_{i}" for i in range(3)]].to_numpy(float)
def calfit(train):
 m=LogisticRegression(C=0.05,max_iter=1000)
 m.fit(np.log(np.clip(mat(train,"raw"),0.005,1)),train.actual.to_numpy(int))
 return m
cal=calfit(train)
def probs(f):
 raw=mat(f,"raw");book=mat(f,"book")
 calibrated=cal.predict_proba(np.log(np.clip(raw,0.005,1)))
 return {"raw":raw,"calibrated":calibrated,"bookmaker":book,
 "blend_25":0.75*calibrated+0.25*book,
 "blend_50":0.5*calibrated+0.5*book,
 "blend_75":0.25*calibrated+0.75*book}
rows=[]
for period,f in [("train_2021_2024",train),("test_2025",valid[valid.year==2025]),("test_2026",valid[valid.year==2026]),("test_2025_2026",valid)]:
 if f.empty:continue
 odds=mat(f,"price");actual=f.actual.to_numpy(int)
 for model,p in probs(f).items():
  brier=np.mean(np.sum((p-np.eye(3)[actual])**2,axis=1))/3
  ll=log_loss(actual,p,labels=[0,1,2])
  ev=p*odds-1
  side=ev.argmax(axis=1);best=ev[np.arange(len(f)),side]
  for threshold in [0.05,0.15,0.30]:
   for cap in [3,6,20]:
    chosen=(best>=threshold)&(odds[np.arange(len(f)),side]<cap)
    idx=np.where(chosen)[0]
    returns=np.where(actual[idx]==side[idx],odds[idx,side[idx]]-1,-1)
    rows.append(dict(period=period,model=model,threshold=threshold,odds_cap=cap,fixtures=len(f),brier=brier,log_loss=ll,bets=len(idx),roi=float(returns.mean()) if len(idx) else np.nan,units=float(returns.sum()),predicted_roi=float(best[idx].mean()) if len(idx) else np.nan,avg_odds=float(odds[idx,side[idx]].mean()) if len(idx) else np.nan))
out=pd.DataFrame(rows)
os.makedirs("research_results",exist_ok=True)
out.to_csv("research_results/match_odds_value_selection_diagnostic.csv",index=False)
print(out[(out.period=="test_2025_2026")&(out.threshold==0.05)&(out.odds_cap==20)].to_string(index=False),flush=True)
