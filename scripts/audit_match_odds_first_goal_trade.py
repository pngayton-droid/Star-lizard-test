"""Chronological Match Matrix selection and first-goal trading feasibility audit.
No historical in-play exchange lay quotes: report event outcomes, NOT invented trading ROI.
"""
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
timelines={}
for rec in fetch("historical_match_events","match_id,timeline_data"):
 events=((rec.get("timeline_data") or {}).get("events") or [])
 if events:timelines[rec["match_id"]]=events
eligible=data[(data.date>=pd.Timestamp("2021-01-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.match_id.isin(quotes)&data.match_id.isin(timelines)].sort_values(["date","match_id"])
rows=[]
def norm(s):return "".join(ch for ch in str(s).lower() if ch.isalnum())
for i,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="strength").head(250)
 sample=sample[sample.hg.notna()&sample.ag.notna()]
 if len(sample)<50:continue
 historical={"home":float(np.mean(sample.hg>sample.ag)),"away":float(np.mean(sample.hg<sample.ag))}
 candidates=[]
 for side in ("home","away"):
  try:price=float((quotes[r.match_id].get(side) or {}).get("last_seen"))
  except (ValueError,TypeError,AttributeError):continue
  if not 1.2<=price<=20:continue
  ev=historical[side]*price-1
  if ev>=0.05:candidates.append((ev,side,price))
 if not candidates:continue
 ev,side,price=max(candidates)
 goals=[]
 for e in timelines[r.match_id]:
  if e.get("type") not in ("goal","own_goal"):continue
  team=norm((e.get("team") or {}).get("name"))
  if team==norm(r.home):scorer="home"
  elif team==norm(r.away):scorer="away"
  else:continue
  if e["type"]=="own_goal":scorer="away" if scorer=="home" else "home"
  try:minute=int(e["minute"])
  except (ValueError,TypeError,KeyError):continue
  goals.append((minute,int(e.get("sequence") or 0),scorer))
 goals.sort()
 # Only use verified attribution: final goal counts must agree with recorded score.
 if sum(g[2]=="home" for g in goals)!=int(r.hg) or sum(g[2]=="away" for g in goals)!=int(r.ag):continue
 for cutoff in (60,70,80):
  early=[g for g in goals if g[0]<=cutoff]
  outcome=("no_goal_by_exit" if not early else ("scored_first" if early[0][2]==side else "conceded_first"))
  rows.append(dict(match_id=r.match_id,year=int(r.date.year),side=side,price=price,predicted_roi=ev,cutoff=cutoff,outcome=outcome,first_goal_minute=goals[0][0] if goals else None,full_time_win=int((r.hg>r.ag) if side=="home" else (r.ag>r.hg))))
 if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
df=pd.DataFrame(rows)
if df.empty:raise RuntimeError("No verified trading selections")
os.makedirs("research_results",exist_ok=True)
df.to_csv("research_results/match_odds_first_goal_trade_bets.csv",index=False)
summary=df.groupby(["cutoff","outcome"],observed=True).agg(matches=("match_id","size"),avg_back_odds=("price","mean"),avg_first_goal_minute=("first_goal_minute","mean")).reset_index()
summary["total"]=summary.groupby("cutoff")["matches"].transform("sum")
summary["pct"]=100*summary.matches/summary.total
summary.to_csv("research_results/match_odds_first_goal_trade_summary.csv",index=False)
print("NO IN-PLAY LAY PRICES AVAILABLE: ROI CANNOT BE CALCULATED",flush=True)
print(summary.to_string(index=False),flush=True)
