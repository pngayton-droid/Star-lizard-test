"""Odds-band audit of existing chronological Matrix 1X2 and goal-timeline results.
No changes to model; no invented in-play prices.
"""
import os
import numpy as np
import pandas as pd
os.makedirs("research_results",exist_ok=True)
bins=[1.2,1.5,2,3,4,6,20.00001]
labels=["1.20-1.49","1.50-1.99","2.00-2.99","3.00-3.99","4.00-5.99","6.00-20.00"]
bet=pd.read_csv("research_results/match_odds_matrix_full_bets.csv")
bet=bet[bet.price_type=="last_seen"].copy()
bet["odds_band"]=pd.cut(bet.price,bins=bins,labels=labels,right=False)
bet["win"]=(bet.profit>0).astype(int)
summ=bet.groupby(["odds_band"],observed=True).agg(bets=("profit","size"),roi=("profit","mean"),units=("profit","sum"),strike_rate=("win","mean"),predicted_roi=("predicted_roi","mean"),avg_odds=("price","mean")).reset_index()
year=bet.groupby(["odds_band","year"],observed=True).agg(bets=("profit","size"),roi=("profit","mean"),units=("profit","sum")).reset_index()
summ.to_csv("research_results/match_odds_band_roi.csv",index=False)
year.to_csv("research_results/match_odds_band_year.csv",index=False)
print("OUTRIGHT",summ.to_string(index=False),flush=True)
trade=pd.read_csv("research_results/match_odds_first_goal_trade_bets.csv")
trade["odds_band"]=pd.cut(trade.price,bins=bins,labels=labels,right=False)
out=trade.groupby(["cutoff","odds_band","outcome"],observed=True).agg(matches=("match_id","size")).reset_index()
tot=trade.groupby(["cutoff","odds_band"],observed=True).agg(total=("match_id","size"),avg_odds=("price","mean"),ft_win_rate=("full_time_win","mean")).reset_index()
out=out.merge(tot,on=["cutoff","odds_band"],how="left")
out["pct"]=out.matches/out.total
out.to_csv("research_results/match_odds_band_trading.csv",index=False)
trade_year=trade.groupby(["cutoff","odds_band","year","outcome"],observed=True).agg(matches=("match_id","size")).reset_index()
trade_year.to_csv("research_results/match_odds_band_trading_year.csv",index=False)
print("TRADING",out.to_string(index=False),flush=True)
# Predeclared broad filter comparisons, NOT a discovered profitable rule.
for lo,hi in [(1.2,3),(1.5,3),(2,3),(3,6),(6,20.00001)]:
 s=bet[(bet.price>=lo)&(bet.price<hi)]
 print("FILTER",lo,hi,"bets",len(s),"ROI",round(s.profit.mean(),5) if len(s) else None,flush=True)
print("Trading first-goal results cannot establish exchange trading ROI without historical in-play lay prices.",flush=True)
