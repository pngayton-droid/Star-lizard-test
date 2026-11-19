"""Paired chronological test: production Match Matrix vs adding last-five venue shots on target.
Only saved Supabase data; no API requests; never change dashboard model.
"""
import os,ast,json
import numpy as np,pandas as pd
from supabase import create_client
from collections import defaultdict,deque
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
 out=[]
 for start in range(0,100000,1000):
  batch=db.table(table).select(cols).range(start,start+999).execute().data or []
  out+=batch
  if len(batch)<1000:break
 return out
def load():
 df=pd.DataFrame(fetch("historical_xg","match_id,match_date,competition_id,home_team,away_team,home_goals,away_goals,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_xg,away_xg"))
 df.match_date=pd.to_datetime(df.match_date)
 for c in ["home_goals","away_goals","home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg","home_xg","away_xg"]:df[c]=pd.to_numeric(df[c],errors="coerce")
 return df.sort_values(["match_date","match_id"]).reset_index(drop=True)
def match_corners_cards():
 rows=[]
 for item in fetch("historical_match_events","match_id,stats_data"):
  stats=item.get("stats_data") or {}
  overview=stats.get("overview") or {}
  rec={"match_id":item["match_id"]}
  for key,prefix in (("corner_kicks","corners"),("yellow_cards","yellows")):
   sides=((overview.get(key) or {}).get("all") or {})
   for side in ("home","away"):
    try:rec[f"{prefix}_{side}"]=float(sides[side])
    except (ValueError,TypeError,KeyError):rec[f"{prefix}_{side}"]=np.nan
  sides=(((stats.get("shots") or {}).get("shots_on_target") or {}).get("all") or {})
  for side in ("home","away"):
   try:rec[f"sot_{side}"]=float(sides[side])
   except (ValueError,TypeError,KeyError):rec[f"sot_{side}"]=np.nan
  rows.append(rec)
 return pd.DataFrame(rows)
src=open("pages/Similarity_Pricing.py",encoding="utf-8").read()
tree=ast.parse(src)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features","analogues","market_results","opponent_adjusted_xg"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())
original_analogues=analogues
def analogues_shots(df,target,mode,cutoff,max_distance,feature_set="combined"):
 # Reproduce exact original matching, with optional shots fields added to the distance calculation.
 # New candidate distances are computed from original distances and original active-field count.
 # Instead use a patched copy of the original function to preserve weighting and quality gate.
 return shot_analogues(df,target,mode,cutoff,max_distance,feature_set)
fn=next(n for n in nodes if n.name=="analogues")
fn=ast.fix_missing_locations(fn)
fsource=ast.unparse(fn)
fsource=fsource.replace("def analogues(","def shot_analogues(",1)
needle="    odds_enabled = all("
assert needle in fsource
fsource=fsource.replace(needle,'    if feature_set in ("combined","strength"):\n        fields.update({"h_sot":2.0,"a_sot":2.0,"h_sot_allowed":2.0,"a_sot_allowed":2.0})\n'+needle,1)
exec(fsource,globals())
print("LOAD",flush=True)
data=features()
raw=load()
stats=match_corners_cards()[["match_id","sot_home","sot_away"]]
raw=raw.merge(stats,on="match_id",how="left")
# Rolling venue form strictly before kickoff; group by league, team, venue.
for side in ("home","away"):
 key="home_team" if side=="home" else "away_team"
 for value,out in ((f"sot_{side}",f"{side[0]}_sot"),("sot_away" if side=="home" else "sot_home",f"{side[0]}_sot_allowed")):
  raw[out]=raw.groupby(["competition_id",key],sort=False)[value].transform(lambda x:x.shift(1).rolling(5,min_periods=3).mean())
data=data.merge(raw[["match_id","h_sot","a_sot","h_sot_allowed","a_sot_allowed"]],on="match_id",how="left",validate="one_to_one")
eligible=data[(data.date>=pd.Timestamp("2025-07-01"))&data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.h_xg.notna()&data.a_xg.notna()].sort_values(["date","match_id"])
selected=eligible.iloc[np.unique(np.linspace(0,len(eligible)-1,min(300,len(eligible)),dtype=int))]
print("TEST_FIXTURES",len(selected),flush=True)
rows=[]
for i,r in enumerate(selected.itertuples(index=False)):
 target=r._asdict()
 for k in ("market_home","market_draw","market_away"):target[k]=np.nan
 for feature_set,markets in (("strength",("Home win","Draw","Away win")),("combined",("Over 2.5 goals","BTTS Yes"))):
  for variant,func in (("Original",original_analogues),("With shots on target",shot_analogues)):
   sample=func(data,target,"Pre-match",r.date,2.0,feature_set=feature_set).head(250)
   if len(sample)<30:continue
   result=market_results(sample,"Pre-match")
   actual={"Home win":int(r.hg>r.ag),"Draw":int(r.hg==r.ag),"Away win":int(r.hg<r.ag),"Over 2.5 goals":int(r.hg+r.ag>=3),"BTTS Yes":int(r.hg>0 and r.ag>0)}
   for market in markets:
    wins,n=result[market]
    if n<30:continue
    p=wins/n;y=actual[market]
    rows.append(dict(match_id=r.match_id,period="2025" if r.date<pd.Timestamp("2026-01-01") else "2026",feature_set=feature_set,variant=variant,market=market,probability=p,actual=y,brier=(p-y)**2,analogues=n))
 if (i+1)%25==0:print("PROGRESS",i+1,flush=True)
df=pd.DataFrame(rows)
paired=df.pivot_table(index=["match_id","market"],columns="variant",values="brier").dropna().index
df=df.set_index(["match_id","market"]).loc[paired].reset_index()
summary=df.groupby(["period","market","variant"],as_index=False).agg(tests=("actual","size"),brier=("brier","mean"),predicted=("probability","mean"),actual=("actual","mean"),median_analogues=("analogues","median"))
all_summary=df.groupby(["market","variant"],as_index=False).agg(tests=("actual","size"),brier=("brier","mean"),predicted=("probability","mean"),actual=("actual","mean"),median_analogues=("analogues","median"))
os.makedirs("research_results",exist_ok=True)
df.to_csv("research_results/shots_similarity_detail.csv",index=False)
summary.to_csv("research_results/shots_similarity_by_period.csv",index=False)
all_summary.to_csv("research_results/shots_similarity_summary.csv",index=False)
print(all_summary.to_string(index=False),flush=True)
