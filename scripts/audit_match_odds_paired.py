"""Chronological Match Matrix card totals against saved Bet365 prices.\nAll fixtures included; red cards provisionally count as two additional cards.\nNot exact Bet365 settlement: second-yellow dismissals and recipient eligibility unknown.\n"""
import os,ast
import numpy as np,pandas as pd
from supabase import create_client
from collections import defaultdict,deque
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
 out=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(cols).range(start,start+999).execute().data or []
  out.extend(batch)
  if len(batch)<1000:break
 return out
def import_functions(path,names):
 tree=ast.parse(open(path,encoding="utf-8").read())
 nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
 for n in nodes:n.decorator_list=[]
 exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),path,"exec"),globals())
import_functions("pages/Similarity_Pricing.py",{"season","features","analogues","opponent_adjusted_xg"})
import_functions("scripts/test_shots_similarity.py",{"load","match_corners_cards"})
data=features()
quotes={}
for rec in fetch("historical_match_odds","match_id,odds_payload"):
 for b in (((rec.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []):
  if b.get("bookmaker")=="Bet365":
   quotes[rec["match_id"]]=(b.get("markets") or {}).get("match_odds") or {}
   break

eligible=data[(data.date>=pd.Timestamp("2021-01-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.match_id.isin(quotes)].sort_values(["date","match_id"])
rows=[]; bets=[]
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 prior=data[(data.date<r.date)&data.hg.notna()&data.ag.notna()&(data.league==r.league)]
 if len(prior)<100:continue
 actual="home" if r.hg>r.ag else ("draw" if r.hg==r.ag else "away")
 truth=np.array([float(actual==side) for side in ("home","draw","away")])
 base=np.array([(prior.hg>prior.ag).mean(),(prior.hg==prior.ag).mean(),(prior.hg<prior.ag).mean()])
 samples={}
 for config in ("combined","strength"):
  sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set=config)
  if len(sample)<50:break
  samples[config]=sample
 if len(samples)!=2:continue
 for config,sample in samples.items():
  probs=np.array([(sample.hg>sample.ag).mean(),(sample.hg==sample.ag).mean(),(sample.hg<sample.ag).mean()])
  for limit in ("all","250"):
   pp=probs if limit=="all" else np.array([(sample.head(250).hg>sample.head(250).ag).mean(),(sample.head(250).hg==sample.head(250).ag).mean(),(sample.head(250).hg<sample.head(250).ag).mean()])
   rows.append(dict(match_id=r.match_id,year=int(r.date.year),config=config,limit=limit,analogues=len(sample) if limit=="all" else min(250,len(sample)),brier=float(np.mean((pp-truth)**2)),baseline_brier=float(np.mean((base-truth)**2))))
   for price_type in ("opening","last_seen"):
    candidates=[]
    for j,side in enumerate(("home","draw","away")):
     try:price=float((quotes[r.match_id].get(side) or {}).get(price_type))
     except (ValueError,TypeError,AttributeError):continue
     if not 1.2<=price<=20:continue
     ev=float(pp[j]*price-1)
     candidates.append((ev,side,price))
    if not candidates:continue
    ev,side,price=max(candidates)
    if ev>=0.05:
     bets.append(dict(match_id=r.match_id,year=int(r.date.year),config=config,limit=limit,price_type=price_type,side=side,price=price,predicted_roi=ev,profit=price-1 if side==actual else -1))
 if (i+1)%250==0:print("PROGRESS",i+1,len(eligible),flush=True)
os.makedirs("research_results",exist_ok=True)
scores=pd.DataFrame(rows);trades=pd.DataFrame(bets)
if scores.empty or trades.empty:raise RuntimeError("No paired results")
scores.to_csv("research_results/match_odds_paired_accuracy_detail.csv",index=False)
trades.to_csv("research_results/match_odds_paired_bets.csv",index=False)
a=scores.groupby(["config","limit"],as_index=False).agg(fixtures=("match_id","size"),brier=("brier","mean"),baseline_brier=("baseline_brier","mean"),average_analogues=("analogues","mean"))
a["brier_improvement"]=a.baseline_brier-a.brier
b=trades.groupby(["config","limit","price_type"],as_index=False).agg(bets=("profit","size"),roi=("profit","mean"),predicted_roi=("predicted_roi","mean"),units=("profit","sum"))
a.to_csv("research_results/match_odds_paired_accuracy_summary.csv",index=False)
b.to_csv("research_results/match_odds_paired_roi_summary.csv",index=False)
print("ACCURACY",a.to_string(index=False),flush=True)
print("BETTING",b.to_string(index=False),flush=True)
