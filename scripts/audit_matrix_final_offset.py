"""FINAL capped 1X2 test. Preregistered: gain >=.001, week-bootstrap CI>0, >=4/5 years.
Market is FIXED offset: p=softmax(log(q)+X @ beta). No production changes.
Historical dates and last-seen odds have NOT been independently timestamp verified.
"""
import os
from collections import defaultdict
import numpy as np
import pandas as pd
from scipy.optimize import minimize

f=pd.read_csv("research_results/matrix_draw_full_history_forecasts.csv")
f.date=pd.to_datetime(f.date,errors="coerce")
required=["date","actual","home","away"]+[f"price_{i}" for i in range(3)]+[f"raw_{i}" for i in range(3)]
f=f.dropna(subset=required).sort_values(["date","match_id"]).reset_index(drop=True)
prices=f[[f"price_{i}" for i in range(3)]].to_numpy(float)
valid=np.isfinite(prices).all(axis=1)&(prices>1).all(axis=1)
f=f.loc[valid].reset_index(drop=True);prices=prices[valid]
a=f.actual.to_numpy(int)
inv=1/prices
q=inv/inv.sum(axis=1,keepdims=True)
# Power de-vig: solve sum(inv**exponent)=1 per match.
from scipy.optimize import brentq
exponents=np.array([brentq(lambda k:np.sum(row**k)-1,.5,5) if row.sum()>1 else 1. for row in inv])
qp=inv**exponents[:,None];qp/=qp.sum(axis=1,keepdims=True)
raw=np.clip(f[[f"raw_{i}" for i in range(3)]].to_numpy(float),.01,1)
raw/=raw.sum(axis=1,keepdims=True)
resid=np.clip(np.log(raw[:,[0,2]]/raw[:,[1,1]])-np.log(q[:,[0,2]]/q[:,[1,1]]),-2,2)
for c in ["h_ppg","a_ppg","h_gdpg","a_gdpg","h_form","a_form","h_rank","a_rank"]:
 f[c]=pd.to_numeric(f[c],errors="coerce")
for name,h,away in [("ppg","h_ppg","a_ppg"),("gd","h_gdpg","a_gdpg"),("form","h_form","a_form")]:
 f[name+"_diff"]=f[h]-f[away]
f["rank_diff"]=f.a_rank-f.h_rank
# Elo: sequential by match DATE. Same-day matches are rated from the start-of-day snapshot.
# Subset-only ratings; team names may not be globally unique. This is a limitation.
ratings=defaultdict(lambda:1500.)
elo=np.zeros(len(f))
for date,group in f.groupby("date",sort=True):
 changes=defaultdict(float)
 for idx,row in group.iterrows():
  home=str(row.home);away=str(row.away)
  rh=ratings[home];ra=ratings[away]
  elo[idx]=(rh-ra)/400.
  expected=1/(1+10**((ra-rh-65)/400))
  score=1. if row.actual==0 else (.5 if row.actual==1 else 0.)
  delta=20*(score-expected)
  changes[home]+=delta;changes[away]-=delta
 for team,delta in changes.items():ratings[team]+=delta
f["elo_diff"]=elo
features=["ppg_diff","gd_diff","form_diff","rank_diff","elo_diff"]
f["matrix_0"]=resid[:,0];f["matrix_1"]=resid[:,1]
specs={"OFFSET_STRENGTH":features,"OFFSET_STRENGTH_MATRIX":features+["matrix_0","matrix_1"],"OFFSET_ELO_ONLY":["elo_diff"]}
def fit_predict(tr,te,cols,market):
 if not cols:return market[te]
 train=f.loc[tr,cols].copy();test=f.loc[te,cols].copy()
 median=train.median().fillna(0)
 train=train.fillna(median).to_numpy(float);test=test.fillna(median).to_numpy(float)
 mu=train.mean(axis=0);sd=np.maximum(train.std(axis=0),1e-6)
 train=np.clip((train-mu)/sd,-5,5);test=np.clip((test-mu)/sd,-5,5)
 y=a[tr];off=np.log(np.clip(market[tr],1e-8,1))
 def probs(x,offset,beta):
  logits=offset+x@beta
  logits-=logits.max(axis=1,keepdims=True)
  ex=np.exp(logits)
  return ex/ex.sum(axis=1,keepdims=True)
 def objective(v):
  beta=v.reshape((train.shape[1],3))
  p=probs(train,off,beta)
  loss=-np.log(np.maximum(p[np.arange(len(y)),y],1e-12)).sum()+10*np.sum(beta**2)
  grad=train.T@(p-np.eye(3)[y])+20*beta
  return loss,grad.ravel()
 result=minimize(objective,np.zeros(train.shape[1]*3),jac=True,method="L-BFGS-B",options={"maxiter":200})
 if not result.success:print("optimizer warning",result.message,flush=True)
 return probs(test,np.log(np.clip(market[te],1e-8,1)),result.x.reshape((test.shape[1],3)))
period=f.date.dt.to_period("M")
records=[]
for month in sorted(period.unique()):
 tr=np.flatnonzero((period<month)&(f.date>=pd.Timestamp("2021-01-01")))
 te=np.flatnonzero(period==month)
 if len(tr)<3000 or len(te)<20:continue
 for devig,market in [("proportional",q),("power",qp)]:
  for model,cols in [("RAW_MARKET",[]),*specs.items()]:
   p=fit_predict(tr,te,cols,market)
   for j,k in enumerate(te):
    records.append(dict(match_id=f.at[k,"match_id"],date=str(f.at[k,"date"].date()),year=int(f.at[k,"date"].year),devig=devig,model=model,actual=int(a[k]),logloss=-np.log(max(p[j,a[k]],1e-12))))
pred=pd.DataFrame(records)
if pred.empty:raise RuntimeError("No scored months")
rng=np.random.default_rng(20261119)
results=[];years=[]
for devig in ("proportional","power"):
 pivot=pred[pred.devig==devig].pivot(index="match_id",columns="model",values="logloss")
 meta=pred[(pred.devig==devig)&(pred.model=="RAW_MARKET")].set_index("match_id").loc[pivot.index]
 weeks=pd.to_datetime(meta.date).dt.to_period("W").astype(str).to_numpy()
 _,wi=np.unique(weeks,return_inverse=True)
 for model in specs:
  gain=(pivot.RAW_MARKET-pivot[model]).to_numpy()
  sums=np.bincount(wi,weights=gain);counts=np.bincount(wi)
  draws=rng.integers(len(sums),size=(2000,len(sums)))
  boot=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
  byyear={int(y):float(gain[meta.year.to_numpy()==y].mean()) for y in sorted(meta.year.unique())}
  positive=sum(x>0 for x in byyear.values())
  lower=float(np.quantile(boot,.025));upper=float(np.quantile(boot,.975))
  results.append(dict(devig=devig,model=model,fixtures=len(gain),gain=float(gain.mean()),ci_low=lower,ci_high=upper,positive_years=positive,years=len(byyear),pass_rule=bool(gain.mean()>=.001 and lower>0 and positive>=4)))
  for y,g in byyear.items():years.append(dict(devig=devig,model=model,year=y,gain=g))
os.makedirs("research_results",exist_ok=True)
pd.DataFrame(results).to_csv("research_results/matrix_final_offset_summary.csv",index=False)
pd.DataFrame(years).to_csv("research_results/matrix_final_offset_by_year.csv",index=False)
print(pd.DataFrame(results).to_string(index=False),flush=True)
print("LIMITATIONS: dates not verified kickoff timestamps; Bet365 last_seen timestamp not independently verified; Elo uses only eligible subset; inspected historical years; no independent holdout.",flush=True)
