"""Predeclared Match Matrix probability vs Betfair odds, on identical strong-away matches.
Historical analogues strictly precede kickoff; no TheStatsAPI requests.
Results saved to repo for direct retrieval. No optimisation on the test period.
"""
import os,ast,json
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
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in {"season","features","analogues"}]
for n in nodes:n.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),"Similarity_Pricing.py","exec"),globals())
print("LOAD",flush=True)
data=features()
odds=[]
for item in fetch("historical_match_odds","match_id,odds_payload"):
 for book in (((item.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []):
  if str(book.get("name") or book.get("bookmaker") or book.get("id") or "")!="Betfair Exchange":continue
  m=(book.get("markets") or {}).get("match_odds") or {}
  try:prices=[float((m.get(k) or {}).get("opening")) for k in ("home","draw","away")]
  except (TypeError,ValueError):continue
  if min(prices)<=1 or max(prices)>1000 or not 0.95<=sum(1/x for x in prices)<=1.30:continue
  odds.append({"match_id":item["match_id"],"betfair_open":prices[2]})
quotes=pd.DataFrame(odds).sort_values(["match_id","betfair_open"]).drop_duplicates("match_id")
eligible=data.merge(quotes,on="match_id",how="inner")
eligible=eligible[(eligible.a_ppg>eligible.h_ppg)&((eligible.a_gdpg-eligible.h_gdpg)>=0.5)&(eligible.date>=pd.Timestamp("2026-01-01"))].sort_values(["date","match_id"])
print("ELIGIBLE",len(eligible),flush=True)
rows=[]
for idx,r in enumerate(eligible.itertuples(index=False)):
 target=r._asdict()
 for key in ("market_home","market_draw","market_away"):target[key]=np.nan
 matches=analogues(data,target,"Pre-match",r.date,2.0,feature_set="strength")
 if len(matches)<30:continue
 p=float((matches.ag>matches.hg).mean())
 price=float(r.betfair_open)
 win=int(r.ag>r.hg)
 net_price=1+(price-1)*0.98
 edge=p*net_price-1
 rows.append({"match_id":r.match_id,"date":str(r.date.date()),"league":r.league,"n_analogues":len(matches),"away_win":win,"model_away_probability":p,"betfair_open":price,"net_price_2pct":net_price,"model_edge_2pct":edge,"profit_all":win*(net_price-1)-(1-win)})
 if (idx+1)%25==0:print("PROGRESS",idx+1,flush=True)
result=pd.DataFrame(rows)
if result.empty:raise SystemExit("No qualifying model forecasts")
result["date"]=pd.to_datetime(result.date)
# These are descriptive bins, not newly fitted thresholds. No future odds/results in feature construction.
result["band"]=pd.cut(result.model_edge_2pct,[-np.inf,-0.05,0,0.05,np.inf],labels=["below -5%","-5% to 0%","0% to +5%","above +5%"])
summary=[]
def add(name,sub):
 if sub.empty:return
 summary.append({"group":name,"matches":len(sub),"wins":int(sub.away_win.sum()),"win_rate":round(sub.away_win.mean(),5),"avg_model_probability":round(sub.model_away_probability.mean(),5),"avg_model_edge":round(sub.model_edge_2pct.mean(),5),"roi_after_simulated_2pct":round(sub.profit_all.mean(),5),"mean_opening_odds":round(sub.betfair_open.mean(),4)})
add("All Betfair-qualified matches",result)
for name,g in result.groupby("band",observed=True):add("Edge band "+str(name),g)
for cutoff in (0,0.05,0.10):
 add("Bet when model edge >= "+str(cutoff),result[result.model_edge_2pct>=cutoff])
for month,g in result.groupby(result.date.dt.to_period("M").astype(str)):add("Month "+month,g)
# Compare probability quality to exchange implied probability, removing 2% only from profit.
result["market_implied_probability"]=1/result.betfair_open
print("BRIER",{"model":round(float(np.mean((result.model_away_probability-result.away_win)**2)),6),"raw_exchange_implied":round(float(np.mean((result.market_implied_probability-result.away_win)**2)),6)},flush=True)
for item in summary:print("RESULT",json.dumps(item),flush=True)
os.makedirs("research_results",exist_ok=True)
result.to_csv("research_results/strong_away_model_vs_betfair_detail.csv",index=False)
pd.DataFrame(summary).to_csv("research_results/strong_away_model_vs_betfair_summary.csv",index=False)
with open("research_results/strong_away_model_vs_betfair_report.json","w") as f:json.dump({"qualifying_matches":len(result),"summary":summary,"notes":["Chronological analogues; historical features available before match","Model is previously inspected; not an untouched independent holdout","2% hypothetical exchange commission on winnings; liquidity unverified"]},f,indent=2)
print("DONE_MODEL_VS_BETFAIR",flush=True)
