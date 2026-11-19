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
source=open("pages/Similarity_Pricing.py",encoding="utf-8").read()
# Restore uncapped matching for a valid comparison with the old behaviour.
source=source.replace('return pool.loc[pool["distance"]<=max_distance].sort_values("distance").head(400)','return pool.loc[pool["distance"]<=max_distance].sort_values("distance")')
tree=ast.parse(source)
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features","analogues","market_results","opponent_adjusted_xg","upcoming_target"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())



fixtures=[
("12:30","Manchester City","Fulham"),
("15:00","Bournemouth","Nottingham Forest"),
("15:00","Aston Villa","Sunderland"),
("15:00","Chelsea","Leeds United"),
("15:00","Coventry City","Crystal Palace"),
("15:00","Tottenham Hotspur","Ipswich Town"),
("17:30","Newcastle United","Arsenal")]
print("BUILDING_FEATURES",flush=True)
df=features()
out=[]
for kickoff,home,away in fixtures:
 match={"date":pd.Timestamp("2026-11-21",tz="Europe/London"),"home":home,"away":away,"league":"comp_3039"}
 target=upcoming_target(df,match)
 if pd.isna(target["h_ppg"]) or pd.isna(target["a_ppg"]):
  print("SKIPPED",home,away,"insufficient current-season strength",flush=True)
  continue
 target.update({"market_home":np.nan,"market_draw":np.nan,"market_away":np.nan})
 for feature_set in ("combined","strength"):
  sample=analogues(df,target,"Pre-match",target["date"],2.0,feature_set=feature_set).head(250)
  result=market_results(sample,"Pre-match") if len(sample) else {}
  names=("Home win","Draw","Away win") if feature_set=="strength" else ("Over 1.5 goals","Over 2.5 goals","Over 3.5 goals","BTTS Yes","Over 8.5 corners","Over 9.5 corners","Over 10.5 corners","Over 3.5 yellow cards","Over 4.5 yellow cards","Over 5.5 yellow cards")
  for name in names:
   hits,n=result.get(name,(0,0))
   out.append({"date":"2026-11-21","kickoff_gmt":kickoff,"home":home,"away":away,"market":name,"model":feature_set,"comparable_matches":n,"wins":hits,"probability":round(hits/n,6) if n else None,"fair_odds":round(n/hits,3) if hits else None})
 print("DONE",home,away,flush=True)
os.makedirs("research_results",exist_ok=True)
pd.DataFrame(out).to_csv("research_results/saturday_2026_11_21_matrix_prices.csv",index=False)
print(pd.DataFrame(out).to_string(index=False),flush=True)
