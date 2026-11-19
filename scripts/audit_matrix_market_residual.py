"""Market-anchored 1X2 residual models, strictly expanding monthly backtest.
M0: bookmaker no-vig log ratios; M1: M0 + pre-match strength;
M2: M1 + Matrix log ratios. Fixed regularisation; no threshold tuning.
Note: historical years have been inspected; this is research, not untouched validation.
"""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import log_loss

f=pd.read_csv("research_results/matrix_draw_full_history_forecasts.csv")
f["date"]=pd.to_datetime(f.date,errors="coerce")
f=f.dropna(subset=["date","actual"]+[f"price_{i}" for i in range(3)]+[f"raw_{i}" for i in range(3)])
f=f.sort_values(["date","match_id"]).reset_index(drop=True)
price=f[[f"price_{i}" for i in range(3)]].to_numpy(float)
raw=np.clip(f[[f"raw_{i}" for i in range(3)]].to_numpy(float),.005,1)
inv=1/price
market=inv/inv.sum(axis=1,keepdims=True)
f["market_home"]=market[:,0];f["market_draw"]=market[:,1];f["market_away"]=market[:,2]
# Market relative logits, not probabilities treated as independent features.
m=np.log(np.clip(market[:,[0,2]],.001,1)/np.clip(market[:,[1,1]],.001,1))
r=np.log(raw[:,[0,2]]/raw[:,[1,1]])
strength_cols=["h_ppg","a_ppg","h_gdpg","a_gdpg","h_form","a_form","h_rank","a_rank"]
for c in strength_cols:f[c]=pd.to_numeric(f[c],errors="coerce")
# Missing values replaced using training medians INSIDE each month; missingness flags added.
f["ppg_diff"]=f.h_ppg-f.a_ppg
f["gd_diff"]=f.h_gdpg-f.a_gdpg
f["form_diff"]=f.h_form-f.a_form
f["rank_diff"]=f.a_rank-f.h_rank
strength=["ppg_diff","gd_diff","form_diff","rank_diff"]
for i in range(2):
 f[f"market_log_{i}"]=m[:,i]
 f[f"matrix_resid_{i}"]=r[:,i]-m[:,i]
base=["market_log_0","market_log_1"]
models={"M0_market_calibrated":base,"M1_market_plus_strength":base+strength,"M2_plus_matrix_residual":base+strength+["matrix_resid_0","matrix_resid_1"]}
dates=f.date.dt.to_period("M")
all_rows=[];pred_rows=[]
for month in sorted(dates.unique()):
 train=(dates<month)&(f.date>=pd.Timestamp("2021-01-01"))
 test=dates==month
 if train.sum()<3000 or test.sum()<20:continue
 yt=f.loc[train,"actual"].to_numpy(int)
 yy=f.loc[test,"actual"].to_numpy(int)
 if len(np.unique(yt))!=3:continue
 idx=np.flatnonzero(test)
 for name,cols in models.items():
  tr=f.loc[train,cols].copy();te=f.loc[test,cols].copy()
  med=tr.median().fillna(0)
  tr=tr.fillna(med).to_numpy(float);te=te.fillna(med).to_numpy(float)
  # Strong shrinkage for incremental information; fixed hyperparameter C.
  clf=make_pipeline(StandardScaler(),LogisticRegression(C=.05,max_iter=1000))
  clf.fit(tr,yt)
  p=np.clip(clf.predict_proba(te),1e-8,1)
  p/=p.sum(axis=1,keepdims=True)
  for j,k in enumerate(idx):
   item=f.iloc[k]
   row=dict(match_id=item.match_id,date=str(item.date.date()),year=int(item.year),month=str(month),model=name,actual=int(yy[j]),p_home=float(p[j,0]),p_draw=float(p[j,1]),p_away=float(p[j,2]),price_home=float(price[k,0]),price_draw=float(price[k,1]),price_away=float(price[k,2]),market_home=float(market[k,0]),market_draw=float(market[k,1]),market_away=float(market[k,2]))
   pred_rows.append(row)
  score=-np.log(p[np.arange(len(yy)),yy])
  all_rows.append(dict(month=str(month),year=int(month.year),model=name,fixtures=len(yy),logloss=float(score.mean()),brier=float(np.mean(np.sum((p-np.eye(3)[yy])**2,axis=1)/3))))
 # no-vig bookmaker benchmark
 mp=market[idx]
 all_rows.append(dict(month=str(month),year=int(month.year),model="BOOKMAKER_NO_VIG",fixtures=len(yy),logloss=float(-np.log(mp[np.arange(len(yy)),yy]).mean()),brier=float(np.mean(np.sum((mp-np.eye(3)[yy])**2,axis=1)/3))))
if not pred_rows:raise RuntimeError("No monthly out-of-sample predictions")
pred=pd.DataFrame(pred_rows)
scores=pd.DataFrame(all_rows)
# Every fixture has exactly one prediction from each model. Use paired differences.
pivot=pred.pivot(index="match_id",columns="model",values=["p_home","p_draw","p_away"])
meta=pred[pred.model=="M0_market_calibrated"].set_index("match_id")
a=meta.actual.to_numpy(int)
per={}
for model in models:
 p=np.column_stack([pivot[("p_home",model)],pivot[("p_draw",model)],pivot[("p_away",model)]])
 per[model]=-np.log(np.clip(p[np.arange(len(a)),a],1e-8,1))
results=[]
rng=np.random.default_rng(20261119)
weeks=meta.date.apply(lambda x:str(pd.Timestamp(x).to_period("W"))).to_numpy()
uniq,wi=np.unique(weeks,return_inverse=True)
for name in ("M1_market_plus_strength","M2_plus_matrix_residual"):
 diff=per["M0_market_calibrated"]-per[name]
 # Cluster bootstrap by calendar week, paired across models.
 cluster_sum=np.bincount(wi,weights=diff,minlength=len(uniq))
 cluster_n=np.bincount(wi,minlength=len(uniq))
 draws=rng.integers(0,len(uniq),size=(2000,len(uniq)))
 boot=cluster_sum[draws].sum(axis=1)/cluster_n[draws].sum(axis=1)
 results.append(dict(comparison=name+" minus M0",fixtures=len(diff),logloss_gain=float(diff.mean()),ci_low=float(np.quantile(boot,.025)),ci_high=float(np.quantile(boot,.975)),positive_years=int(sum(np.mean(diff[meta.year.to_numpy()==y])>0 for y in sorted(meta.year.unique()))),years=len(meta.year.unique())))
summary=pd.DataFrame(results)
os.makedirs("research_results",exist_ok=True)
scores.to_csv("research_results/matrix_market_residual_monthly.csv",index=False)
summary.to_csv("research_results/matrix_market_residual_summary.csv",index=False)
pred.to_csv("research_results/matrix_market_residual_predictions.csv",index=False)
print(summary.to_string(index=False),flush=True)
print(scores.groupby(["year","model"]).apply(lambda d:pd.Series({"fixtures":d.fixtures.sum(),"logloss":np.average(d.logloss,weights=d.fixtures),"brier":np.average(d.brier,weights=d.fixtures)}),include_groups=False).to_string(),flush=True)
