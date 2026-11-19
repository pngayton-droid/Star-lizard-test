"""Predeclared Match Matrix probability vs Betfair odds, on identical strong-away matches.
Historical analogues strictly precede kickoff; no TheStatsAPI requests.
Results saved to repo for direct retrieval. No optimisation on the test period.
"""
import os,ast,json
from collections import defaultdict,deque
import numpy as np,pandas as pd
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,columns):
 rows=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(columns).range(start,start+999).execute().data or []
  rows.extend(batch)
  if len(batch)<1000:break
 return rows
def load():
 cols="match_id,match_date,competition_id,home_team,away_team,home_goals,away_goals,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_xg,away_xg"
 df=pd.DataFrame(fetch("historical_xg",cols))
 df["match_date"]=pd.to_datetime(df.match_date)
 for c in ["home_goals","away_goals","home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg","home_xg","away_xg"]:df[c]=pd.to_numeric(df[c],errors="coerce")
 return df.sort_values(["match_date","match_id"]).reset_index(drop=True)
def match_corners_cards():
 rows=[]
 for item in fetch("historical_match_events","match_id,stats_data"):
  overview=((item.get("stats_data") or {}).get("overview") or {})
  rec={"match_id":item["match_id"]}
  for key,prefix in (("corner_kicks","corners"),("yellow_cards","yellows")):
   sides=((overview.get(key) or {}).get("all") or {})
   for side in ("home","away"):
    try:rec[f"{prefix}_{side}"]=float(sides[side])
    except (ValueError,TypeError,KeyError):rec[f"{prefix}_{side}"]=np.nan
  rows.append(rec)
 return pd.DataFrame(rows,columns=["match_id","corners_home","corners_away","yellows_home","yellows_away"])
tree=ast.parse(open("pages/Similarity_Pricing.py",encoding="utf-8").read())
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features","analogues","market_results","opponent_adjusted_xg"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())


print("LOAD",flush=True)
data=features()
eligible=data[(data.date>=pd.Timestamp("2025-07-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.h_xg.notna()&data.a_xg.notna()].sort_values(["date","match_id"])
selected=eligible.iloc[np.unique(np.linspace(0,len(eligible)-1,min(240,len(eligible)),dtype=int))]
print("TEST_FIXTURES",len(selected),flush=True)
rows=[];coverage=[]
for i,r in enumerate(selected.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 prior=data[(data.date<r.date)&data.hg.notna()&data.ag.notna()]
 baseline=prior[prior.league==r.league]
 if len(baseline)<100:continue
 actual={"Home win":int(r.hg>r.ag),"Draw":int(r.hg==r.ag),"Away win":int(r.hg<r.ag),"Over 2.5 goals":int(r.hg+r.ag>=3),"BTTS Yes":int(r.hg>0 and r.ag>0)}
 if pd.notna(r.corners_home) and pd.notna(r.corners_away):actual["Over 9.5 corners"]=int(r.corners_home+r.corners_away>=10)
 if pd.notna(r.yellows_home) and pd.notna(r.yellows_away):actual["Over 4.5 yellow cards"]=int(r.yellows_home+r.yellows_away>=5)
 # Compare previous unlimited matching, current 400 nearest, and 100 nearest, each with same coverage fallback.
 for model,cap in (("Unlimited",None),("Nearest 400",400),("Nearest 100",100)):
  for fs in ("combined","strength"):
   pool=analogues(data,target,"Pre-match",r.date,2.0,feature_set=fs)
   if cap is not None:pool=pool.head(cap)
   bands={name:pool[pool.distance<=limit] for name,limit in (("Close",1.0),("Moderate",1.5),("Broad",2.0))}
   chosen=next((name for name in ("Close","Moderate","Broad") if len(bands[name])>=100),next((name for name in ("Broad","Moderate","Close") if len(bands[name])>=30),next((name for name in ("Broad","Moderate","Close") if len(bands[name])>0,"None")))
   sample=bands.get(chosen,pool.iloc[:0])
   coverage.append({"match_id":r.match_id,"model":model,"feature_set":fs,"band":chosen,"analogues":len(sample),"usable_30":int(len(sample)>=30),"usable_100":int(len(sample)>=100)})
   if len(sample)<30:continue
   results=market_results(sample,"Pre-match")
   for market,y in actual.items():
    if (fs=="strength") != (market in ("Home win","Draw","Away win")):continue
    wins,n=results.get(market,(0,0))
    if n<30:continue
    rows.append({"match_id":r.match_id,"model":model,"market":market,"predicted":wins/n,"actual":y,"brier":(wins/n-y)**2,"analogues":n})
 if (i+1)%40==0:print("PROGRESS",i+1,flush=True)
result=pd.DataFrame(rows); cov=pd.DataFrame(coverage)
if result.empty:raise RuntimeError("No forecasts")
wide=result.pivot_table(index=["match_id","market"],columns="model",values="brier",aggfunc="first").dropna()
ids=set(map(tuple,wide.index.tolist()))
paired=result[result.apply(lambda x:(x.match_id,x.market) in ids,axis=1)]
summary=paired.groupby(["market","model"],as_index=False).agg(tests=("actual","size"),brier=("brier","mean"),mean_predicted=("predicted","mean"),actual_rate=("actual","mean"),median_analogues=("analogues","median"))
coverage_summary=cov.groupby(["model","feature_set"],as_index=False).agg(fixtures=("match_id","size"),usable_30=("usable_30","sum"),usable_100=("usable_100","sum"),median_analogues=("analogues","median"))
os.makedirs("research_results",exist_ok=True)
result.to_csv("research_results/matching_cap_detail.csv",index=False)
summary.to_csv("research_results/matching_cap_summary.csv",index=False)
cov.to_csv("research_results/matching_cap_coverage_detail.csv",index=False)
coverage_summary.to_csv("research_results/matching_cap_coverage_summary.csv",index=False)
with open("research_results/matching_cap_report.json","w") as f:json.dump({"fixtures_tested":len(selected),"paired_cases":len(ids),"method":"Chronological recent historical fixtures; cap 100/400/unlimited, close/moderate/broad fallback, 30 minimum; 1X2 strength-only; other markets combined; exploratory not untouched holdout","summary":summary.round(6).to_dict("records"),"coverage":coverage_summary.to_dict("records")},f,indent=2)
print(summary.to_string(index=False),flush=True)
print(coverage_summary.to_string(index=False),flush=True)
