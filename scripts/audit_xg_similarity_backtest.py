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
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features","analogues","market_results"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())

print("LOAD",flush=True)
data=features()
eligible=data[(data.date>=pd.Timestamp("2025-07-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.h_xg.notna()&data.a_xg.notna()].sort_values(["date","match_id"])
selected=eligible.iloc[np.unique(np.linspace(0,len(eligible)-1,min(240,len(eligible)),dtype=int))]
print("TEST_FIXTURES",len(selected),flush=True)
rows=[]
for i,r in enumerate(selected.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 prior=data[(data.date<r.date)&data.hg.notna()&data.ag.notna()]
 baseline=prior[prior.league==r.league]
 if len(baseline)<100:continue
 old=dict(target,h_xg=np.nan,a_xg=np.nan)
 variants={"Without xG":analogues(data,old,"Pre-match",r.date,1.5,"combined"),
           "With real xG":analogues(data,target,"Pre-match",r.date,1.5,"combined"),
           "League baseline":baseline}
 actual={"Home win":int(r.hg>r.ag),"Draw":int(r.hg==r.ag),"Away win":int(r.hg<r.ag),"Over 2.5 goals":int(r.hg+r.ag>=3),"BTTS Yes":int(r.hg>0 and r.ag>0)}
 if pd.notna(r.corners_home) and pd.notna(r.corners_away):actual["Over 9.5 corners"]=int(r.corners_home+r.corners_away>=10)
 if pd.notna(r.yellows_home) and pd.notna(r.yellows_away):actual["Over 4.5 yellow cards"]=int(r.yellows_home+r.yellows_away>=5)
 for name,sample in variants.items():
  if len(sample)<30:continue
  estimates=market_results(sample,"Pre-match")
  for market,y in actual.items():
   wins,n=estimates.get(market,(0,0))
   if n<30:continue
   p=wins/n
   rows.append({"match_id":r.match_id,"date":str(r.date.date()),"model":name,"market":market,"n_analogues":n,"predicted":p,"actual":y,"brier":(p-y)**2})
 if (i+1)%40==0:print("PROGRESS",i+1,flush=True)
result=pd.DataFrame(rows)
if result.empty:raise RuntimeError("No forecasts produced")
# Fair comparison: only fixture/market pairs available for all three variants.
wide=result.pivot_table(index=["match_id","market"],columns="model",values="brier",aggfunc="first").dropna()
ids=set(map(tuple,wide.index.tolist()))
paired=result[result.apply(lambda r:(r.match_id,r.market) in ids,axis=1)]
summary=paired.groupby(["market","model"],as_index=False).agg(tests=("actual","size"),brier=("brier","mean"),mean_predicted=("predicted","mean"),actual_rate=("actual","mean"),median_analogues=("n_analogues","median"))
os.makedirs("research_results",exist_ok=True)
result.to_csv("research_results/xg_similarity_backtest_detail.csv",index=False)
summary.to_csv("research_results/xg_similarity_backtest_summary.csv",index=False)
with open("research_results/xg_similarity_backtest_report.json","w") as f:json.dump({"fixtures_tested":len(selected),"paired_fixture_market_cases":len(ids),"summary":summary.round(6).to_dict("records"),"method":"Chronological pre-match data; 1.5 similarity cutoff; identical matched cases; no goal-substituted xG; 240 evenly spaced recent fixtures; not an untouched holdout"},f,indent=2)
print(summary.to_string(index=False),flush=True)
