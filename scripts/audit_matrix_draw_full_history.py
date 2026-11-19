"""Full-history Matrix draw audit, with strictly pre-match team-strength diagnostics.
The 3.50-3.99 band was discovered on 2025-26 and is NOT independent validation.
Raw Matrix forecasts are available for all years; calibration is trained on 2021-24
and only scored out-of-sample on 2025+.
"""
import os, ast
from collections import defaultdict, deque
import numpy as np
import pandas as pd
from supabase import create_client
from sklearn.linear_model import LogisticRegression
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def fetch(table,cols):
    out=[]
    for start in range(0,100000,1000):
        batch=db.table(table).select(cols).range(start,start+999).execute().data or []
        out.extend(batch)
        if len(batch)<1000:break
    return out
def import_functions(path,names):
    tree=ast.parse(open(path,encoding="utf-8").read())
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    for n in nodes:n.decorator_list=[]
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),path,"exec"),globals())
import_functions("pages/Similarity_Pricing.py",{"season","features","analogues","opponent_adjusted_xg"})
import_functions("scripts/test_shots_similarity.py",{"load","match_corners_cards"})
data=features()
quotes={}
for rec in fetch("historical_match_odds","match_id,odds_payload"):
    for b in (((rec.get("odds_payload") or {}).get("data") or {}).get("bookmakers") or []):
        if b.get("bookmaker")=="Bet365":
            quotes[rec["match_id"]]=(b.get("markets") or {}).get("match_odds") or {}
            break
eligible=data[data.hg.notna()&data.ag.notna()&data.h_ppg.notna()&data.a_ppg.notna()&data.match_id.isin(quotes)].sort_values(["date","match_id"])
rows=[]
for i,r in enumerate(eligible.itertuples(index=False)):
    try: prices=np.array([float((quotes[r.match_id].get(s) or {}).get("last_seen")) for s in ("home","draw","away")])
    except (ValueError,TypeError,AttributeError):continue
    if not np.all(np.isfinite(prices)) or np.any((prices<1.2)|(prices>20)):continue
    target=r._asdict()
    for k in ("market_home","market_draw","market_away"):target[k]=np.nan
    sample=analogues(data,target,"Pre-match",r.date,2.0,feature_set="combined").head(250)
    if len(sample)<50:continue
    raw=np.array([(sample.hg>sample.ag).mean(),(sample.hg==sample.ag).mean(),(sample.hg<sample.ag).mean()])
    raw=np.clip(raw,.005,.995);raw/=raw.sum()
    rows.append(dict(match_id=r.match_id,date=str(r.date.date()),year=int(r.date.year),league=r.league,home=r.home,away=r.away,
        actual=0 if r.hg>r.ag else (1 if r.hg==r.ag else 2),
        h_ppg=r.h_ppg,a_ppg=r.a_ppg,ppg_gap=abs(r.h_ppg-r.a_ppg),
        h_gdpg=r.h_gdpg,a_gdpg=r.a_gdpg,gd_gap=abs(r.h_gdpg-r.a_gdpg),
        h_rank=r.h_rank,a_rank=r.a_rank,rank_gap=abs(r.h_rank-r.a_rank) if pd.notna(r.h_rank) and pd.notna(r.a_rank) else np.nan,
        h_form=r.h_form,a_form=r.a_form,form_gap=abs(r.h_form-r.a_form) if pd.notna(r.h_form) and pd.notna(r.a_form) else np.nan,
        **{f"raw_{j}":raw[j] for j in range(3)},**{f"price_{j}":prices[j] for j in range(3)}))
    if (i+1)%250==0:print("PROGRESS",i+1,"/",len(eligible),flush=True)
f=pd.DataFrame(rows)
if f.empty:raise RuntimeError("No eligible full-history matches")
training=f[(f.year>=2021)&(f.year<=2024)]
if len(training)<1000:raise RuntimeError("Insufficient 2021-24 calibration training")
cols=[f"raw_{i}" for i in range(3)]
cal=LogisticRegression(C=.05,max_iter=1000)
cal.fit(np.log(np.clip(training[cols].to_numpy(float),.005,1)),training.actual.to_numpy(int))
f["p_raw_draw"]=f.raw_1
f["p_calibrated_draw"]=np.nan
future=f.year>=2025
f.loc[future,"p_calibrated_draw"]=cal.predict_proba(np.log(np.clip(f.loc[future,cols].to_numpy(float),.005,1)))[:,1]
f["draw_price"]=f.price_1
f["draw_won"]=f.actual.eq(1)
f["favourite_price"]=f[["price_0","price_2"]].min(axis=1)
f["draw_band"]=np.where((f.draw_price>=3.5)&(f.draw_price<4),"3.50-3.99","other")
f["raw_ev"]=f.p_raw_draw*f.draw_price-1
f["calibrated_ev"]=f.p_calibrated_draw*f.draw_price-1
f["raw_pick"]=f.raw_ev>=.05
f["calibrated_pick"]=future&(f.calibrated_ev>=.05)
f["profit"]=np.where(f.draw_won,f.draw_price-1,-1)
f["period"]=np.where(f.year<2021,"pre_2021_raw_only",np.where(f.year<=2024,"2021_2024_calibration_training","2025_2026_out_of_sample"))
def band(s,bins,labels):
    return pd.cut(s,bins=bins,labels=labels,include_lowest=True,right=False)
f["ppg_gap_band"]=band(f.ppg_gap,[0,.25,.5,1,np.inf],["<0.25","0.25-0.49","0.50-0.99","1.00+"])
f["gd_gap_band"]=band(f.gd_gap,[0,.25,.5,1,np.inf],["<0.25","0.25-0.49","0.50-0.99","1.00+"])
f["rank_gap_band"]=band(f.rank_gap,[0,3,6,11,np.inf],["0-2","3-5","6-10","11+"])
f["form_gap_band"]=band(f.form_gap,[0,.5,1,2,np.inf],["<0.5","0.5-0.99","1.00-1.99","2.00+"])
f["favourite_band"]=band(f.favourite_price,[0,1.5,2,2.5,np.inf],["<1.50","1.50-1.99","2.00-2.49","2.50+"])
def summary(frame,keys,method):
    selected=frame[frame[method+"_pick"]].copy()
    if selected.empty:return pd.DataFrame()
    result=selected.groupby(keys,dropna=False,observed=True).agg(bets=("match_id","size"),wins=("draw_won","sum"),units=("profit","sum"),avg_odds=("draw_price","mean"),avg_ppg_gap=("ppg_gap","mean"),avg_gd_gap=("gd_gap","mean"),avg_rank_gap=("rank_gap","mean")).reset_index()
    result["roi"]=result.units/result.bets
    result["method"]=method
    return result
summaries=[]
for method in ("raw","calibrated"):
    for keys in (["period","year","draw_band"],["period","draw_band"],["period","draw_band","ppg_gap_band"],["period","draw_band","gd_gap_band"],["period","draw_band","rank_gap_band"],["period","draw_band","form_gap_band"],["period","draw_band","favourite_band"]):
        r=summary(f,keys,method)
        if len(r):
            r["breakdown"]=",".join(keys)
            summaries.append(r)
out=pd.concat(summaries,ignore_index=True)
os.makedirs("research_results",exist_ok=True)
f.to_csv("research_results/matrix_draw_full_history_forecasts.csv",index=False)
out.to_csv("research_results/matrix_draw_full_history_summary.csv",index=False)
print("ELIGIBLE YEARS",f.groupby("year").size().to_dict(),flush=True)
print(out[(out.breakdown=="period,year,draw_band")&(out.draw_band=="3.50-3.99")].to_string(index=False),flush=True)
