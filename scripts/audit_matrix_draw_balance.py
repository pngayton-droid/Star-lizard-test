"""Draw-only selection: market balance and favourite-strength diagnostic.
Uses frozen pre-match Matrix probabilities and Bet365 last-seen 1X2 prices.
Market price balance is a PROXY for team strength, not independently computed PPG.
"""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
df=pd.read_csv("research_results/match_odds_calibration_forecasts.csv")
train=df[df.year<=2024]
cal=LogisticRegression(C=.05,max_iter=1000)
cols=[f"raw_{i}" for i in range(3)]
cal.fit(np.log(np.clip(train[cols].to_numpy(float),.005,1)),train.actual.to_numpy(int))
out=[]
for year in [2025,2026]:
 d=df[df.year==year].copy()
 p=cal.predict_proba(np.log(np.clip(d[cols].to_numpy(float),.005,1)))
 odds=d[[f"price_{i}" for i in range(3)]].to_numpy(float)
 implied=1/odds;implied/=implied.sum(axis=1,keepdims=True)
 # The implied probability difference between home and away captures market-perceived mismatch.
 balance=np.abs(implied[:,0]-implied[:,2])
 fav_price=np.minimum(odds[:,0],odds[:,2])
 draw_price=odds[:,1]
 draw_ev=p[:,1]*draw_price-1
 actual=d.actual.to_numpy(int)
 groups={
  "all":np.ones(len(d),bool),
  "balanced_gap_lt_0.10":balance<.10,
  "moderate_gap_0.10_0.20":(balance>=.10)&(balance<.20),
  "uneven_gap_0.20_0.35":(balance>=.20)&(balance<.35),
  "strong_fav_gap_ge_0.35":balance>=.35,
  "favourite_below_1.50":fav_price<1.50,
  "favourite_1.50_1.99":(fav_price>=1.50)&(fav_price<2),
  "favourite_2.00_2.49":(fav_price>=2)&(fav_price<2.5),
  "favourite_2.50_plus":fav_price>=2.5,
  "draw_price_below_3.00":draw_price<3,
  "draw_price_3.00_3.49":(draw_price>=3)&(draw_price<3.5),
  "draw_price_3.50_3.99":(draw_price>=3.5)&(draw_price<4),
  "draw_price_4.00_plus":draw_price>=4,
 }
 for threshold in (.05,.15):
  for group,mask in groups.items():
   ix=np.flatnonzero(mask&(draw_ev>=threshold))
   returns=np.where(actual[ix]==1,draw_price[ix]-1,-1)
   out.append(dict(year=year,threshold=threshold,group=group,fixtures_in_group=int(mask.sum()),bets=len(ix),wins=int((actual[ix]==1).sum()),roi=float(returns.mean()) if len(ix) else np.nan,units=float(returns.sum()),predicted_roi=float(draw_ev[ix].mean()) if len(ix) else np.nan,avg_odds=float(draw_price[ix].mean()) if len(ix) else np.nan))
r=pd.DataFrame(out)
both=r.groupby(["threshold","group"],as_index=False).agg(fixtures_in_group=("fixtures_in_group","sum"),bets=("bets","sum"),wins=("wins","sum"),units=("units","sum"))
both["roi"]=both.units/both.bets.replace(0,np.nan)
both["win_rate"]=both.wins/both.bets.replace(0,np.nan)
os.makedirs("research_results",exist_ok=True)
r.to_csv("research_results/matrix_draw_balance_by_year.csv",index=False)
both.to_csv("research_results/matrix_draw_balance_summary.csv",index=False)
print(both[both.threshold==.05].to_string(index=False),flush=True)
