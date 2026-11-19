"""One-off strong-away-team validation using REAL opening decimal odds, not normalized implied fair odds.
Predeclared GD-gap filters: >=0.5 and >=1.0; 2026 is untouched chronological holdout.
No TheStatsAPI requests. This research does not authorize live betting.
"""
import os,ast
import numpy as np,pandas as pd
from collections import defaultdict,deque
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
 rows=[]
 for i in range(0,100000,1000):
  b=db.table(table).select(cols).range(i,i+999).execute().data or []
  rows.extend(b)
  if len(b)<1000:break
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
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"dashboard_features","exec"),globals())
print("LOADING",flush=True)
df=features()
print("FEATURES",len(df),flush=True)
# Preserve actual executable quotes by bookmaker. Do NOT normalize bookmaker margin away.
records=[]
for row in fetch("historical_match_odds","match_id,odds_payload"):
 books=((row.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []
 for b in books:
  market=(b.get("markets") or {}).get("match_odds") or {}
  try:prices=[float((market.get(k) or {}).get("opening")) for k in ("home","draw","away")]
  except (ValueError,TypeError):continue
  if min(prices)<=1 or max(prices)>1000:continue
  margin=sum(1/x for x in prices)
  if not 0.95<=margin<=1.30:continue
  name=str(b.get("name") or b.get("bookmaker") or b.get("id") or "Unknown")
  records.append({"match_id":row["match_id"],"bookmaker":name,"home_odds":prices[0],"draw_odds":prices[1],"away_odds":prices[2]})
quotes=pd.DataFrame(records,columns=["match_id","bookmaker","home_odds","draw_odds","away_odds"])
print("VALID_QUOTES",len(quotes),"unique_matches",quotes.match_id.nunique(),flush=True)
if quotes.empty:raise SystemExit("No actual opening prices in historical_match_odds; cannot establish ROI")
# Predefine best AVAILABLE odds across recorded bookmakers as an optimistic ceiling; also show median.
agg=quotes.groupby("match_id",as_index=False).agg(away_odds_best=("away_odds","max"),away_odds_median=("away_odds","median"),books=("bookmaker","nunique"))
d=df.merge(agg,on="match_id",how="left",validate="one_to_one")
d=d[d.hg.notna()&d.ag.notna()&d.h_ppg.notna()&d.a_ppg.notna()&d.h_gdpg.notna()&d.a_gdpg.notna()].copy()
d["away_superior"]=(d.a_ppg>d.h_ppg)&(d.a_gdpg>d.h_gdpg)
d["gd_gap"]=d.a_gdpg-d.h_gdpg
d["away_win"]=(d.ag>d.hg).astype(int)
d["period"]=np.where(d.date<pd.Timestamp("2026-01-01"),"Discovery before 2026","Holdout 2026")
d["profit_best"]=np.where(d.away_win==1,d.away_odds_best-1,-1)
d["profit_median"]=np.where(d.away_win==1,d.away_odds_median-1,-1)
d["fair_odds"]=np.nan
summary=[]
for period in ("Discovery before 2026","Holdout 2026"):
 for threshold in (0,0.5,1.0):
  all_eligible=d[(d.period==period)&d.away_superior&(d.gd_gap>=threshold)]
  priced=all_eligible.dropna(subset=["away_odds_best","away_odds_median"])
  item={"period":period,"min_gd_gap":threshold,"all_matches":len(all_eligible),"all_win_rate":round(all_eligible.away_win.mean(),5) if len(all_eligible) else None,"priced_matches":len(priced),"priced_win_rate":round(priced.away_win.mean(),5) if len(priced) else None,"best_quote_roi":round(priced.profit_best.mean(),5) if len(priced) else None,"median_quote_roi":round(priced.profit_median.mean(),5) if len(priced) else None,"avg_best_odds":round(priced.away_odds_best.mean(),4) if len(priced) else None}
  summary.append(item);print("RESULT",item,flush=True)
pd.DataFrame(summary).to_csv("strong_away_real_odds_summary.csv",index=False)
d[d.away_superior].to_csv("strong_away_real_odds_detail.csv",index=False)
quotes.to_csv("strong_away_opening_quotes.csv",index=False)
print("DONE",flush=True)
