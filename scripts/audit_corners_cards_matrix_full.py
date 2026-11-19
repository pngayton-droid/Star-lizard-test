"""Chronological full Bet365 corners/cards totals ROI. Cards use a provisional +2/red proxy; not exact settlement."""
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
red_counts={}
for rec in fetch("historical_match_events","match_id,stats_data"):
 red=(((rec.get("stats_data") or {}).get("overview") or {}).get("red_cards") or {}).get("all") or {}
 try:
  if red.get("home") is not None and red.get("away") is not None:red_counts[rec["match_id"]]=int(red["home"])+int(red["away"])
 except (ValueError,TypeError):pass
data["red_total"]=data.match_id.map(red_counts)
quotes={}
for rec in fetch("historical_match_odds","match_id,odds_payload"):
 for b in (((rec.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []):
  if b.get("bookmaker")=="Bet365":
   markets=b.get("markets") or {}
   quotes[rec["match_id"]]={"corners":markets.get("match_corners") or {},"cards":markets.get("total_cards") or {}}
   break
eligible=data[(data.date>=pd.Timestamp("2021-01-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.match_id.isin(quotes)].sort_values(["date","match_id"])
rows=[]
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="combined").head(250)
 if len(sample)<50:continue
 for market in ("corners","cards"):
  if market=="corners":
   if pd.isna(r.corners_home) or pd.isna(r.corners_away):continue
   hist=(sample.corners_home+sample.corners_away).dropna().to_numpy()
   actual=float(r.corners_home+r.corners_away)
  else:
   if pd.isna(r.yellows_home) or pd.isna(r.yellows_away) or pd.isna(r.red_total):continue
   hist=(sample.yellows_home+sample.yellows_away+2*sample.red_total).dropna().to_numpy()
   actual=float(r.yellows_home+r.yellows_away+2*r.red_total)
  if len(hist)<50:continue
  for price_type in ("opening","last_seen"):
   candidates=[]
   for key,prices in quotes[r.match_id][market].items():
    try:line=float(key)
    except (TypeError,ValueError):continue
    if abs(line%1-0.5)>1e-6:continue
    for side in ("over","under"):
     try:price=float((prices.get(side) or {}).get(price_type))
     except (ValueError,TypeError,AttributeError):continue
     if not 1.2<=price<=20:continue
     prob=float(np.mean(hist>line if side=="over" else hist<line))
     ev=prob*price-1
     profit=price-1 if (actual>line if side=="over" else actual<line) else -1
     candidates.append(dict(match_id=r.match_id,year=int(r.date.year),market=market,side=side,line=line,price_type=price_type,price=price,prob=prob,predicted_roi=ev,profit=profit,analogues=len(hist),red_total=r.red_total))
   if candidates:
    best=max(candidates,key=lambda x:x["predicted_roi"])
    if best["predicted_roi"]>=0.05:rows.append(best)
 if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
df=pd.DataFrame(rows)
os.makedirs("research_results",exist_ok=True)
if df.empty:raise RuntimeError("No selected bets")
df.to_csv("research_results/corners_cards_matrix_full_bets.csv",index=False)
df["odds_band"]=pd.cut(df.price,[1.2,1.5,1.75,2,2.25,2.5,3,4,5,7,10,20.00001],right=False).astype(str)
def agg(cols):
 return df.groupby(cols,observed=True).agg(bets=("profit","size"),roi=("profit","mean"),predicted_roi=("predicted_roi","mean"),units=("profit","sum")).reset_index()
for name,cols in [("year",["market","price_type","year"]),("side",["market","price_type","side"]),("odds",["market","price_type","odds_band","side"]),("year_side",["market","price_type","year","side"]),("line",["market","price_type","line","side"])]:
 a=agg(cols);a.insert(0,"breakdown",name)
 if name=="year":out=[a]
 else:out.append(a)
result=pd.concat(out,ignore_index=True)
result.to_csv("research_results/corners_cards_matrix_full_summary.csv",index=False)
print("TOTAL (OPENING AND LAST-SEEN SEPARATE BET SETS)",len(df),"ROI",df.profit.mean(),flush=True)
print(result.to_string(index=False),flush=True)
