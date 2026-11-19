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


from sklearn.metrics import log_loss
eligible=data[(data.date>=pd.Timestamp("2021-01-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.match_id.isin(quotes)].sort_values(["date","match_id"])
rows=[]
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 candidates=analogues(data,target,"Pre-match",r.date,2.0,feature_set="combined")
 if len(candidates)<50:continue
 try:prices=np.array([float((quotes[r.match_id].get(side) or {}).get("last_seen")) for side in ("home","draw","away")])
 except (ValueError,TypeError,AttributeError):continue
 if not np.all(np.isfinite(prices)) or np.any((prices<1.2)|(prices>20)):continue
 actual=0 if r.hg>r.ag else (1 if r.hg==r.ag else 2)
 # Each variant only uses pre-match fields and strictly prior historical fixtures.
 variants={"combined_250":candidates.head(250)}
 same=candidates[candidates.league==r.league]
 if len(same)>=50:variants["same_league_250"]=same.head(250)
 # Opponent-strength similarity: explicitly match the gap in pre-match PPG/GD,
 # not just each team's independent form. Penalise missing strength.
 if pd.notna(r.h_ppg) and pd.notna(r.a_ppg):
  c=candidates.copy()
  gap=(c.h_ppg-c.a_ppg)-(r.h_ppg-r.a_ppg)
  gd=(c.h_gdpg-c.a_gdpg)-(r.h_gdpg-r.a_gdpg)
  c["strength_distance"]=np.sqrt(c.distance**2+0.7*(gap/0.65).fillna(2.5)**2+0.3*(gd/0.6).fillna(2.5)**2)
  variants["strength_gap_250"]=c.sort_values("strength_distance").head(250)
  if len(same)>=50:
   cs=c[c.league==r.league]
   variants["league_and_strength_250"]=cs.sort_values("strength_distance").head(250)
 for name,sample in variants.items():
  if len(sample)<50:continue
  raw=np.array([(sample.hg>sample.ag).mean(),(sample.hg==sample.ag).mean(),(sample.hg<sample.ag).mean()])
  raw=np.clip(raw,0.005,0.995);raw/=raw.sum()
  rows.append(dict(match_id=r.match_id,year=int(r.date.year),variant=name,actual=actual,n=len(sample),**{f"p_{j}":raw[j] for j in range(3)},**{f"price_{j}":prices[j] for j in range(3)}))
 if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
df=pd.DataFrame(rows)
if df.empty:raise RuntimeError("No valid results")
os.makedirs("research_results",exist_ok=True)
df.to_csv("research_results/match_odds_similarity_quality_forecasts.csv",index=False)
summary=[]
for (year,variant),f in df.groupby(["year","variant"]):
 if year<2025:continue
 p=f[[f"p_{j}" for j in range(3)]].to_numpy()
 odds=f[[f"price_{j}" for j in range(3)]].to_numpy()
 actual=f.actual.to_numpy(int)
 book=1/odds;book/=book.sum(axis=1,keepdims=True)
 for model,prob in [("matrix",p),("bookmaker",book)]:
  brier=float(np.mean(np.sum((prob-np.eye(3)[actual])**2,axis=1))/3)
  ll=float(log_loss(actual,prob,labels=[0,1,2]))
  ev=prob*odds-1
  side=ev.argmax(axis=1)
  pick=(ev[np.arange(len(f)),side]>=0.05) if model=="matrix" else np.zeros(len(f),bool)
  ret=np.where(actual[pick]==side[pick],odds[pick,side[pick]]-1,-1)
  summary.append(dict(year=year,variant=variant,model=model,fixtures=len(f),brier=brier,log_loss=ll,bets=len(ret),roi=float(ret.mean()) if len(ret) else np.nan,units=float(ret.sum())))
out=pd.DataFrame(summary)
out.to_csv("research_results/match_odds_similarity_quality_summary.csv",index=False)
print(out.to_string(index=False),flush=True)
