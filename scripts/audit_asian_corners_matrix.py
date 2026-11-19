"""Chronological Match Matrix Asian corner totals against saved Bet365 prices."""
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
   quotes[rec["match_id"]]=(b.get("markets") or {}).get("match_corners") or {}
   break
eligible=data[(data.date>=pd.Timestamp("2021-01-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.corners_home.notna()&data.corners_away.notna()&data.match_id.isin(quotes)].sort_values(["date","match_id"])
rows=[]
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="combined").head(250)
 sample=sample[sample.corners_home.notna()&sample.corners_away.notna()]
 if len(sample)<50:continue
 total=float(r.corners_home+r.corners_away)
 historical=(sample.corners_home+sample.corners_away).to_numpy()
 candidates=[]
 for key,prices in quotes[r.match_id].items():
  try:line=float(key)
  except (ValueError,TypeError):continue
  if abs(line%1-0.5)>1e-6:continue
  for side in ("over","under"):
   try:price=float((prices.get(side) or {}).get("last_seen"))
   except (ValueError,TypeError,AttributeError):continue
   if not 1.5<=price<=3.0:continue
   prob=float(np.mean(historical>line if side=="over" else historical<line))
   ev=prob*price-1
   profit=(price-1) if (total>line if side=="over" else total<line) else -1
   candidates.append(dict(match_id=r.match_id,year=int(r.date.year),line=line,side=side,price=price,prob=prob,predicted_roi=ev,profit=profit,analogues=len(sample)))
 if candidates:
  # Same selection discipline as goals: choose one highest-predicted-ROI quote per fixture.
  best=max(candidates,key=lambda x:(x["predicted_roi"],-x["line"]))
  if best["predicted_roi"]>=0.05:rows.append(best)
 if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
df=pd.DataFrame(rows)
os.makedirs("research_results",exist_ok=True)
if df.empty:raise RuntimeError("No selected bets")
df.to_csv("research_results/asian_corners_matrix_bets.csv",index=False)
df["odds_band"]=pd.cut(df.price,[1.5,1.75,2,2.25,2.5,2.75,3.00001],right=False).astype(str)
def agg(cols):
 return df.groupby(cols,observed=True).agg(bets=("profit","size"),roi=("profit","mean"),predicted_roi=("predicted_roi","mean"),units=("profit","sum")).reset_index()
for name,cols in [("year",["year"]),("side",["side"]),("line",["line","side"]),("odds",["odds_band","side"]),("year_side",["year","side"])]:
 a=agg(cols);a.insert(0,"breakdown",name)
 if name=="year":out=[a]
 else:out.append(a)
result=pd.concat(out,ignore_index=True)
result.to_csv("research_results/asian_corners_matrix_summary.csv",index=False)
print("TOTAL",len(df),"ROI",df.profit.mean(),flush=True)
print(result.to_string(index=False),flush=True)
