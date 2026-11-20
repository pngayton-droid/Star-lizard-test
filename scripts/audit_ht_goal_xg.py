"""Capped HT goals experiment: baseline vs baseline + HT xG.
Odds OPENING (not last_seen) unless timestamp verification becomes possible.
Red cards unavailable in archive: exclude red-card adjustment and flag limitation.
No dashboard changes or betting ROI claims.
"""
import os,numpy as np,pandas as pd
from supabase import create_client
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import PoissonRegressor
from scipy.stats import poisson
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
 rows=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(cols).range(start,start+999).execute().data or []
  rows+=batch
  if len(batch)<1000:break
 return rows
cols="archive_key,match_date,league,ht_home,ht_away,ft_home,ft_away,ht_xg_home,ht_xg_away,b365_home,b365_draw,b365_away,ht_xg_provisional"
f=pd.DataFrame(fetch("archive_verified_match_research",cols))
if f.empty:raise RuntimeError("No archive rows")
f["date"]=pd.to_datetime(f.match_date,errors="coerce")
numeric=["ht_home","ht_away","ft_home","ft_away","ht_xg_home","ht_xg_away","b365_home","b365_draw","b365_away"]
for c in numeric:f[c]=pd.to_numeric(f[c],errors="coerce")
coverage=f.groupby([f.date.dt.year,"league"],dropna=False).agg(matches=("archive_key","size"),ht_xg=("ht_xg_home",lambda x:x.notna().sum()),odds=("b365_home",lambda x:x.notna().sum())).reset_index()
coverage.to_csv("research_results/ht_goal_xg_coverage.csv",index=False)
f=f.dropna(subset=["date"]+numeric).copy()
f=f[(f[["b365_home","b365_draw","b365_away"]]>1).all(axis=1)]
f=f[(f.ft_home>=f.ht_home)&(f.ft_away>=f.ht_away)]
f["goals_h"]=f.ft_home-f.ht_home;f["goals_a"]=f.ft_away-f.ht_away
inv=1/f[["b365_home","b365_draw","b365_away"]].to_numpy(float)
market=inv/inv.sum(axis=1,keepdims=True)
for i,name in enumerate(["home","draw","away"]):f["market_"+name]=market[:,i]
f=f.sort_values(["date","archive_key"]).reset_index(drop=True)
base=["ht_home","ht_away","market_home","market_draw","market_away"]
extra=["ht_xg_home","ht_xg_away"]
period=f.date.dt.to_period("M")
preds=[]
# Joint score via independent team Poissons, evaluated with joint count log likelihood.
for month in sorted(period.unique()):
 tr=np.flatnonzero((period<month)&(f.date>=pd.Timestamp("2015-01-01")))
 te=np.flatnonzero(period==month)
 if len(tr)<1000 or len(te)<20:continue
 for model,features in [("M0",base),("M1_xg",base+extra)]:
  for side in ("h","a"):
   y=f["goals_"+side].to_numpy()
   scaler=StandardScaler().fit(f.loc[tr,features])
   X=scaler.transform(f.loc[tr,features]);Z=scaler.transform(f.loc[te,features])
   fit=PoissonRegressor(alpha=10.0,max_iter=300).fit(X,y[tr])
   pred=np.maximum(fit.predict(Z),1e-6)
   for j,k in enumerate(te):
    preds.append(dict(archive_key=f.at[k,"archive_key"],date=str(f.at[k,"date"].date()),year=int(f.at[k,"date"].year),model=model,side=side,logloss=float(-poisson.logpmf(int(y[k]),pred[j])),expected=float(pred[j])))
p=pd.DataFrame(preds)
if p.empty:raise RuntimeError("No predictions: inspect historical coverage")
paired=p.pivot(index=["archive_key","date","year"],columns=["model","side"],values="logloss").dropna()
loss0=paired[("M0","h")]+paired[("M0","a")]
loss1=paired[("M1_xg","h")]+paired[("M1_xg","a")]
gain=(loss0-loss1).to_numpy()
meta=paired.index.to_frame(index=False)
weeks=pd.to_datetime(meta.date).dt.to_period("W").astype(str).to_numpy()
_,wi=np.unique(weeks,return_inverse=True)
sums=np.bincount(wi,weights=gain);counts=np.bincount(wi)
rng=np.random.default_rng(20261120)
draws=rng.integers(0,len(sums),size=(3000,len(sums)))
boot=sums[draws].sum(axis=1)/counts[draws].sum(axis=1)
yearly=pd.DataFrame([dict(year=int(y),fixtures=int(sum(meta.year==y)),gain=float(gain[meta.year.to_numpy()==y].mean())) for y in sorted(meta.year.unique())])
lo,hi=np.quantile(boot,[.025,.975]);positive=int(sum(yearly.gain>0))
summary=pd.DataFrame([dict(fixtures=len(gain),gain=float(gain.mean()),ci_low=float(lo),ci_high=float(hi),positive_years=positive,years=len(yearly),pass_rule=bool(gain.mean()>=.001 and lo>0 and positive>=4),usable_matches=len(f),archive_matches=len(coverage) and int(coverage.matches.sum()),red_card_data="NOT AVAILABLE in archive",odds_timestamp="UNVERIFIED historic archive Bet365 odds",ht_xg_provisional="Potential postmatch revisions")])
os.makedirs("research_results",exist_ok=True)
summary.to_csv("research_results/ht_goal_xg_summary.csv",index=False)
yearly.to_csv("research_results/ht_goal_xg_yearly.csv",index=False)
print(summary.to_string(index=False),flush=True)
