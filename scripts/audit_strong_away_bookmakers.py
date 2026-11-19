"""Bookmaker-specific robustness audit for strong away teams.
Uses saved Supabase match and odds data only. No API requests.
Actual opening odds, level stakes, no invented Betfair commission or matched liquidity.
"""
import runpy
import numpy as np
import pandas as pd
x=runpy.run_path("scripts/audit_strong_away_actual_odds.py")
d=x["d"];q=x["quotes"]
base=d[["match_id","date","league","away_superior","gd_gap","away_win"]].copy()
q=q.merge(base,on="match_id",how="inner")
q=q[q.away_superior & (q.gd_gap>=0.5)].copy()
q["profit"]=np.where(q.away_win==1,q.away_odds-1,-1)
# 2% and 5% commission sensitivity: on winnings only; not claims of an actual fee.
for rate in (0.02,0.05):
 q[f"profit_commission_{int(rate*100)}pct"]=np.where(q.away_win==1,(q.away_odds-1)*(1-rate),-1)
q["period"]=np.where(q.date<pd.Timestamp("2026-01-01"),"before_2026","2026")
print("BOOKMAKER_NAMES",q.groupby("bookmaker").match_id.nunique().sort_values(ascending=False).to_dict(),flush=True)
rows=[]
for (period,book),group in q.groupby(["period","bookmaker"]):
 # If same bookmaker has multiple quotes per fixture, use earliest recorded first, avoiding double counting.
 group=group.sort_values(["match_id","away_odds"]).drop_duplicates("match_id")
 n=len(group)
 rows.append({"period":period,"bookmaker":book,"matches":n,"wins":int(group.away_win.sum()),"win_rate":round(group.away_win.mean(),5),"mean_opening_odds":round(group.away_odds.mean(),4),"roi_before_commission":round(group.profit.mean(),5),"roi_if_2pct_win_commission":round(group.profit_commission_2pct.mean(),5),"roi_if_5pct_win_commission":round(group.profit_commission_5pct.mean(),5)})
rows=sorted(rows,key=lambda a:(a["period"],-a["matches"],a["bookmaker"]))
for row in rows:print("BOOKMAKER",row,flush=True)
pd.DataFrame(rows).to_csv("strong_away_bookmaker_breakdown.csv",index=False)
q.to_csv("strong_away_bookmaker_detail.csv",index=False)
# Additional check: calendar month stability, to spot a few clustered wins masquerading as a repeatable edge.
for (month,),g in q.groupby([q.date.dt.to_period("M").astype(str)]):
 g=g.sort_values(["match_id","away_odds"]).drop_duplicates("match_id")
 print("MONTH",month,"matches",len(g),"wins",int(g.away_win.sum()),"best_available_roi",round(g.profit.mean(),4),flush=True)
print("DONE_BOOKMAKER_AUDIT",flush=True)
