"""Same-fixture Betfair vs Bet365 opening-price comparison; Supabase only."""
import runpy
import pandas as pd
import numpy as np
x=runpy.run_path("scripts/audit_strong_away_actual_odds.py")
d=x["d"];q=x["quotes"]
eligible=d[d.away_superior & (d.gd_gap>=0.5)][["match_id","date","away_win","gd_gap"]]
q=q.merge(eligible,on="match_id",how="inner")
q=q[q.bookmaker.isin(["Betfair Exchange","Bet365","Pinnacle"])].copy()
q=q.sort_values(["match_id","bookmaker","away_odds"]).drop_duplicates(["match_id","bookmaker"])
pivot=q.pivot(index="match_id",columns="bookmaker",values="away_odds")
paired=pivot.dropna(subset=["Betfair Exchange","Bet365"]).merge(eligible,on="match_id",how="inner")
paired["betfair_better"]=paired["Betfair Exchange"]>paired["Bet365"]
paired["betfair_net_2pct"]=1+(paired["Betfair Exchange"]-1)*0.98
paired["betfair_net_5pct"]=1+(paired["Betfair Exchange"]-1)*0.95
paired["betfair_after_2pct_better"]=paired.betfair_net_2pct>paired["Bet365"]
paired["betfair_after_5pct_better"]=paired.betfair_net_5pct>paired["Bet365"]
for book,col in [("Bet365","Bet365"),("Betfair gross","Betfair Exchange"),("Betfair net 2%","betfair_net_2pct"),("Betfair net 5%","betfair_net_5pct")]:
 paired[book+"_profit"]=np.where(paired.away_win,paired[col]-1,-1)
print("PAIRED_MATCHES",len(paired),flush=True)
print("PAIR_PRICE",{"betfair_higher_count":int(paired.betfair_better.sum()),"betfair_net_2pct_higher_count":int(paired.betfair_after_2pct_better.sum()),"betfair_net_5pct_higher_count":int(paired.betfair_after_5pct_better.sum()),"equal_gross":int((paired["Betfair Exchange"]==paired["Bet365"]).sum())},flush=True)
for name in ["Bet365","Betfair gross","Betfair net 2%","Betfair net 5%"]:
 print("PAIRED_ROI",name,round(paired[name+"_profit"].mean(),5),flush=True)
for month,g in paired.groupby(paired.date.dt.to_period("M").astype(str)):
 print("MONTH",month,"n",len(g),"bet365_roi",round(g["Bet365_profit"].mean(),5),"betfair_net2_roi",round(g["Betfair net 2%_profit"].mean(),5),flush=True)
# A fixed £1 stake at Betfair cannot be assumed matched. Commission varies by account.
# Quantify threshold: Betfair price must exceed 1+(Bet365-1)/(1-commission).
paired.to_csv("strong_away_paired_exchange_vs_bet365.csv",index=False)
print("DONE_PAIRED",flush=True)
