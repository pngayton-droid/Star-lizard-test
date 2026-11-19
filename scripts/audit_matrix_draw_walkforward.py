"""Walk-forward Matrix draw audit: train ONLY on previous years, test next year.
Predeclared draw band 3.50-3.99 is post-hoc selected from 2025-26.
Earlier years use frozen original raw probabilities, no re-fitting to test years.
"""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
f=pd.read_csv("research_results/matrix_draw_full_history_forecasts.csv")
cols=[f"raw_{j}" for j in range(3)]
rows=[]
for year in sorted(f.year.unique()):
    if year<2022:continue
    train=f[(f.year>=2021)&(f.year<year)].copy()
    test=f[f.year==year].copy()
    if len(train)<250 or len(test)<50:continue
    model=LogisticRegression(C=.05,max_iter=1000)
    model.fit(np.log(np.clip(train[cols].to_numpy(float),.005,1)),train.actual.to_numpy(int))
    p=model.predict_proba(np.log(np.clip(test[cols].to_numpy(float),.005,1)))
    test["p_draw"]=p[:,1]
    test["ev"]=test.p_draw*test.draw_price-1
    test["pick"]=test.ev>=.05
    test["ret"]=np.where(test.actual==1,test.draw_price-1,-1)
    for group,mask in {
        "all_draw_prices":np.ones(len(test),bool),
        "draw_3.50_3.99":(test.draw_price>=3.5)&(test.draw_price<4),
        "draw_4.00_plus":test.draw_price>=4,
        "draw_3.50_3.99_ppg_gap_below_0.50":(test.draw_price>=3.5)&(test.draw_price<4)&(test.ppg_gap<.5),
    }.items():
        x=test[test["pick"]&mask]
        rows.append(dict(year=int(year),train_years=f"2021-{int(year)-1}",training_fixtures=len(train),eligible_fixtures=int(mask.sum()),group=group,bets=len(x),wins=int((x.actual==1).sum()),units=float(x.ret.sum()),roi=float(x.ret.mean()) if len(x) else np.nan,mean_odds=float(x.draw_price.mean()) if len(x) else np.nan,mean_predicted_ev=float(x.ev.mean()) if len(x) else np.nan))
r=pd.DataFrame(rows)
overall=r.groupby("group",as_index=False).agg(bets=("bets","sum"),wins=("wins","sum"),units=("units","sum"))
overall["roi"]=overall.units/overall.bets.replace(0,np.nan)
os.makedirs("research_results",exist_ok=True)
r.to_csv("research_results/matrix_draw_walkforward_by_year.csv",index=False)
overall.to_csv("research_results/matrix_draw_walkforward_summary.csv",index=False)
print(r.to_string(index=False),flush=True)
print(overall.to_string(index=False),flush=True)
