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
rows=[]
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="strength").head(250)
 sample=sample[sample.hg.notna()&sample.ag.notna()]
 if len(sample)<50:continue
 historical={"home":float(np.mean(sample.hg>sample.ag)),"draw":float(np.mean(sample.hg==sample.ag)),"away":float(np.mean(sample.hg<sample.ag))}
 actual="home" if r.hg>r.ag else ("draw" if r.hg==r.ag else "away")
 for price_type in ("opening","last_seen"):
  candidates=[]
  for side in ("home","draw","away"):
   try:price=float((quotes[r.match_id].get(side) or {}).get(price_type))
   except (ValueError,TypeError,AttributeError):continue
   if not 1.2<=price<=20.0:continue
   prob=historical[side]
   ev=prob*price-1
   candidates.append(dict(match_id=r.match_id,year=int(r.date.year),side=side,price_type=price_type,price=price,prob=prob,predicted_roi=ev,profit=(price-1 if side==actual else -1),analogues=len(sample)))
  if candidates:
   best=max(candidates,key=lambda x:x["predicted_roi"])
   if best["predicted_roi"]>=0.05:rows.append(best)
 if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
df=pd.DataFrame(rows)
os.makedirs("research_results",exist_ok=True)
if df.empty:raise RuntimeError("No selected bets")
df.to_csv("research_results/match_odds_matrix_full_bets.csv",index=False)
df["odds_band"]=pd.cut(df.price,[1.2,1.5,2,2.5,3,4,5,7,10,20.00001],right=False).astype(str)
def agg(cols):
 return df.groupby(cols,observed=True).agg(bets=("profit","size"),roi=("profit","mean"),predicted_roi=("predicted_roi","mean"),units=("profit","sum")).reset_index()
for name,cols in [("year",["price_type","year"]),("side",["price_type","side"]),("odds",["price_type","odds_band","side"]),("year_side",["price_type","year","side"])]:
 a=agg(cols);a.insert(0,"breakdown",name)
 if name=="year":out=[a]
 else:out.append(a)
result=pd.concat(out,ignore_index=True)
result.to_csv("research_results/match_odds_matrix_full_summary.csv",index=False)
print("TOTAL (OPENING AND LAST-SEEN SEPARATE BET SETS)",len(df),"ROI",df.profit.mean(),flush=True)
print(result.to_string(index=False),flush=True)
