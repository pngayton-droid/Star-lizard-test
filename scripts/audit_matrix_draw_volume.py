"""Explain why walk-forward calibrated draw selection moved into the 3.50-3.99 band.
Uses frozen historical Matrix forecasts; each year's calibrator fits strictly prior seasons.
Outputs selection rates, predicted vs actual draw probabilities, value bins, and volume.
"""
import os
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
f=pd.read_csv("research_results/matrix_draw_full_history_forecasts.csv")
cols=[f"raw_{i}" for i in range(3)]
rows=[]
detail=[]
for year in sorted(f.year.unique()):
    if year<2022:continue
    train=f[(f.year>=2021)&(f.year<year)]
    test=f[f.year==year].copy()
    if len(train)<250 or len(test)<50:continue
    cal=LogisticRegression(C=.05,max_iter=1000)
    cal.fit(np.log(np.clip(train[cols].to_numpy(float),.005,1)),train.actual.to_numpy(int))
    probs=cal.predict_proba(np.log(np.clip(test[cols].to_numpy(float),.005,1)))
    test["cal_draw"]=probs[:,1]
    test["raw_draw"]=test.raw_1
    test["book_draw"]=1/test.draw_price
    test["cal_ev"]=test.cal_draw*test.draw_price-1
    test["raw_ev"]=test.raw_draw*test.draw_price-1
    test["draw_won"]=test.actual.eq(1)
    test["profit"]=np.where(test.draw_won,test.draw_price-1,-1)
    test["year"]=int(year)
    detail.append(test[["match_id","year","league","draw_price","ppg_gap","raw_draw","cal_draw","book_draw","raw_ev","cal_ev","draw_won","profit"]])
    bands={
      "all":np.ones(len(test),bool),
      "draw_3.50_3.99":(test.draw_price>=3.5)&(test.draw_price<4),
      "draw_4.00_plus":test.draw_price>=4,
      "draw_3.50_3.99_ppg_gap_lt_0.5":(test.draw_price>=3.5)&(test.draw_price<4)&(test.ppg_gap<.5),
    }
    for band,mask in bands.items():
        for method in ("raw","cal"):
            s=test.loc[mask]
            selected=s[s[method+"_ev"]>=.05]
            rows.append(dict(year=int(year),group=band,method=method,eligible=len(s),selected=len(selected),
                selection_rate=len(selected)/len(s) if len(s) else np.nan,
                actual_draw_rate=float(s.draw_won.mean()) if len(s) else np.nan,
                avg_raw_draw=float(s.raw_draw.mean()) if len(s) else np.nan,
                avg_cal_draw=float(s.cal_draw.mean()) if len(s) else np.nan,
                avg_book_draw=float(s.book_draw.mean()) if len(s) else np.nan,
                selected_actual_draw_rate=float(selected.draw_won.mean()) if len(selected) else np.nan,
                selected_predicted_draw_rate=float(selected[method+"_draw"].mean()) if len(selected) else np.nan,
                selected_book_draw_rate=float(selected.book_draw.mean()) if len(selected) else np.nan,
                selected_predicted_ev=float(selected[method+"_ev"].mean()) if len(selected) else np.nan,
                selected_roi=float(selected.profit.mean()) if len(selected) else np.nan,
                selected_units=float(selected.profit.sum()),
                selected_avg_odds=float(selected.draw_price.mean()) if len(selected) else np.nan))
r=pd.DataFrame(rows)
d=pd.concat(detail,ignore_index=True)
os.makedirs("research_results",exist_ok=True)
r.to_csv("research_results/matrix_draw_volume_diagnostic.csv",index=False)
d.to_csv("research_results/matrix_draw_volume_match_details.csv",index=False)
print(r[r.group=="draw_3.50_3.99"].to_string(index=False),flush=True)
