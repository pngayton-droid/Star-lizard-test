"""Compare HT xG with an enhanced pre-HT baseline. Strictly walk-forward.
No live prices, no ROI claims. Missing timelines excluded from paired comparison.
"""
import os
import time
import numpy as np
import pandas as pd
from supabase import create_client
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from scipy.stats import poisson

db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
os.makedirs("research_results",exist_ok=True)
def fetch(table,cols):
    out=[]
    batch_size=50 if table=="historical_match_events" else 1000
    start=0
    while start<100000:
        for attempt in range(4):
            try:
                chunk=db.table(table).select(cols).range(start,start+batch_size-1).execute().data or []
                break
            except Exception as exc:
                if "57014" not in str(exc) or attempt==3:raise
                print(f"Timeout on {table} at {start}, retry {attempt+1}",flush=True)
                time.sleep(2*(attempt+1))
        out.extend(chunk)
        start+=batch_size
        if len(chunk)<batch_size:break
    print(f"Fetched {table}: {len(out)} rows",flush=True)
    return pd.DataFrame(out)

h=fetch("halftime_research_outcomes","competition_id,match_date,home_team,away_team,home_ht_goals,away_ht_goals,home_ht_xg,away_ht_xg,home_goals,away_goals")
b=fetch("starlizard_backtest_1x2","match_date,home_team,away_team,home_price,draw_price,away_price")
x=fetch("historical_xg","match_id,match_date,home_team,away_team")
ev=fetch("historical_match_events","match_id,timeline_data")
# Only actual StatsAPI IDs have event timelines; synthetic legacy rows duplicate fixtures.
x=x[x.match_id.astype(str).str.startswith("mt_")].copy()
key=["match_date","home_team","away_team"]
for label,df in [("HT",h),("odds",b),("match ids",x)]:
    if df.duplicated(key).any():raise RuntimeError("Duplicate keys in "+label)
f=h.merge(b,on=key,validate="one_to_one").merge(x,on=key,validate="one_to_one")
if ev.match_id.duplicated().any():raise RuntimeError("Duplicate timeline match ids")
f=f.merge(ev,on="match_id",how="left",validate="one_to_one")
# Build by row, respecting actual home/away team names.
def features(r):
    data=r.timeline_data if isinstance(r.timeline_data,dict) else {}
    events=data.get("events")
    if not isinstance(events,list):return None
    z={k:0 for k in ["h_shots","a_shots","h_sot","a_sot","h_red","a_red","h_corners","a_corners"]}
    for e in events:
        if not isinstance(e,dict) or e.get("period")!="first_half":continue
        team=e.get("team") or {}
        name=team.get("name") if isinstance(team,dict) else None
        side="h" if name==r.home_team else "a" if name==r.away_team else None
        if not side:continue
        typ=e.get("type")
        if typ=="corner_kick":z[side+"_corners"]+=1
        if typ in ("shot_on_target","shot_off_target","shot_blocked","shot_woodwork"):z[side+"_shots"]+=1
        if typ=="shot_on_target":z[side+"_sot"]+=1
        if typ in ("red_card","yellow_red_card","second_yellow_card"):z[side+"_red"]+=1
    goals=[]
    for e in events:
        if not isinstance(e,dict) or e.get("period")!="second_half" or e.get("type") not in ("goal","penalty_scored","own_goal"):continue
        team=e.get("team") or {}
        name=team.get("name") if isinstance(team,dict) else None
        if name not in (r.home_team,r.away_team):continue
        side="h" if name==r.home_team else "a"
        if e.get("type")=="own_goal":side="a" if side=="h" else "h"
        goals.append((int(e.get("minute") or 0),int(e.get("extra_time") or 0),int(e.get("sequence") or 0),side))
    goals.sort()
    z["first_2h"]=goals[0][3] if goals else "none"
    z["timeline_goals"]=len(goals)
    return z
# Timeline-derived features are available at HT; unverified event-name matches are not imputed.
derived=[features(r) for r in f.itertuples(index=False)]
valid=[i for i,z in enumerate(derived) if z is not None]
f=f.iloc[valid].copy().reset_index(drop=True)
d=pd.DataFrame([derived[i] for i in valid])
f=pd.concat([f.drop(columns=["timeline_data"]),d],axis=1)
num=["home_ht_goals","away_ht_goals","home_ht_xg","away_ht_xg","home_goals","away_goals","home_price","draw_price","away_price"]
for c in num:f[c]=pd.to_numeric(f[c],errors="coerce")
f=f.dropna(subset=num)
f=f[(f[["home_price","draw_price","away_price"]]>1).all(axis=1)]
f=f[(f.home_goals>=f.home_ht_goals)&(f.away_goals>=f.away_ht_goals)].copy()
f["date"]=pd.to_datetime(f.match_date)
f["goals_h"]=f.home_goals-f.home_ht_goals
f["goals_a"]=f.away_goals-f.away_ht_goals
inv=1/f[["home_price","draw_price","away_price"]].to_numpy(float)
m=inv/inv.sum(axis=1,keepdims=True)
for i,k in enumerate(["p_home","p_draw","p_away"]):f[k]=m[:,i]
f["ht_diff"]=f.home_ht_goals-f.away_ht_goals
f["ht_total"]=f.home_ht_goals+f.away_ht_goals
f["score_strength"]=f.ht_diff*(f.p_home-f.p_away)
f["red_any"]=((f.h_red+f.a_red)>0).astype(int)
f=f[f.timeline_goals==(f.goals_h+f.goals_a)].copy()
f=f.sort_values(["date","match_id"]).reset_index(drop=True)
core=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away"]
strong=core+["ht_diff","ht_total","score_strength","h_shots","a_shots","h_sot","a_sot","h_red","a_red"]



from sklearn.linear_model import LogisticRegression
from scipy.special import expit,logit
f["score_key"]=f.home_ht_goals.astype(int).astype(str)+"-"+f.away_ht_goals.astype(int).astype(str)
f["trailing_side"]=np.where(f.ht_diff<0,"h",np.where(f.ht_diff>0,"a","none"))
f["favorite_side"]=np.where(f.p_home>f.p_away,"h","a")
f["favorite_trailing"]=(f.trailing_side==f.favorite_side)&(f.trailing_side!="none")
f["trailing_xg_lead"]=np.where(f.trailing_side=="h",f.home_ht_xg>f.away_ht_xg,np.where(f.trailing_side=="a",f.away_ht_xg>f.home_ht_xg,False))
f["out_next"]=np.where(f.first_2h=="h",0,np.where(f.first_2h=="a",1,2))
# Include direct score-state interactions, because favourites trailing were badly underpredicted.
base=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away","ht_diff","ht_total","score_strength","h_shots","a_shots","h_sot","a_sot","h_corners","a_corners","h_red","a_red","home_ht_xg","away_ht_xg"]
f["favorite_trailing_int"]=f.favorite_trailing.astype(int)
f["favorite_trailing_xg_int"]=(f.favorite_trailing&f.trailing_xg_lead).astype(int)
f["favorite_strength_gap"]=np.where(f.favorite_trailing,f.p_home-f.p_away,0.)
f["trailing_xg_gap"]=np.where(f.trailing_side=="h",f.home_ht_xg-f.away_ht_xg,np.where(f.trailing_side=="a",f.away_ht_xg-f.home_ht_xg,0.))
aug=base+["favorite_trailing_int","favorite_trailing_xg_int","favorite_strength_gap","trailing_xg_gap"]
# Each evaluated month uses earlier months for training. For calibration,
# fit the probability corrector only on predictions made for the most recent
# 6 months of training, with base fitting on dates before that window.
period=f.date.dt.to_period("M")
records=[]
for month in sorted(period.unique()):
    te=np.flatnonzero(period==month)
    tr=np.flatnonzero(period<month)
    if len(tr)<1500 or len(te)<20:continue
    cal_start=month-6
    base_idx=np.flatnonzero(period<cal_start)
    cal_idx=np.flatnonzero((period>=cal_start)&(period<month))
    if len(base_idx)<1000 or len(cal_idx)<200:continue
    models={}
    for name,cols in (("baseline",base),("interactions",aug)):
        scale=StandardScaler().fit(f.loc[base_idx,cols])
        X=scale.transform(f.loc[base_idx,cols])
        clf=LogisticRegression(C=1,max_iter=500).fit(X,f.loc[base_idx,"out_next"])
        cal_p=clf.predict_proba(scale.transform(f.loc[cal_idx,cols]))
        test_p=clf.predict_proba(scale.transform(f.loc[te,cols]))
        # Multinomial calibration: correct each outcome's probability using
        # held-out calibration predictions; not outcomes from evaluation month.
        cal_logits=np.log(np.maximum(cal_p,1e-9))
        test_logits=np.log(np.maximum(test_p,1e-9))
        corrector=LogisticRegression(C=1,max_iter=500).fit(cal_logits,f.loc[cal_idx,"out_next"])
        models[name]=(test_p,corrector.predict_proba(test_logits))
    for j,k in enumerate(te):
        r=f.iloc[k]
        actual=int(r.out_next)
        segment=bool(r.favorite_trailing and r.trailing_xg_lead)
        for name,(raw,calibrated) in models.items():
            for variant,probs in (("raw",raw[j]),("calibrated",calibrated[j])):
                p=np.maximum(probs,1e-9);p=p/p.sum()
                trailing_prob=float(p[0 if r.trailing_side=="h" else 1]) if r.trailing_side!="none" else float("nan")
                records.append(dict(match_id=r.match_id,date=str(r.date.date()),year=int(r.date.year),model=name+"_"+variant,segment=segment,favorite_trailing=bool(r.favorite_trailing),trailing_xg_lead=bool(r.trailing_xg_lead),actual=actual,loss=float(-np.log(p[actual])),brier=float(((p-np.eye(3)[actual])**2).sum()),trailing_prob=trailing_prob,trailing_hit=int(r.first_2h==r.trailing_side)))
p=pd.DataFrame(records)
if p.empty:raise RuntimeError("No evaluated matches")
summary=p.groupby(["model"],as_index=False).agg(fixtures=("match_id","size"),logloss=("loss","mean"),brier=("brier","mean"))
summary.to_csv("research_results/ht_next_calibration_summary.csv",index=False)
segments=[]
for label,mask in (("all",p.match_id.notna()),("favorite_trailing_xg_lead",p.segment),("favorite_trailing",p.favorite_trailing),("trailing_xg_lead",p.trailing_xg_lead)):
    for model,part in p[mask].groupby("model"):
        trailing=part[part.trailing_prob.notna()]
        segments.append(dict(segment=label,model=model,fixtures=len(part),logloss=float(part.loss.mean()),brier=float(part.brier.mean()),observed_trailing_next=float(trailing.trailing_hit.mean()) if len(trailing) else float("nan"),predicted_trailing_next=float(trailing.trailing_prob.mean()) if len(trailing) else float("nan"),calibration_gap=float(trailing.trailing_hit.mean()-trailing.trailing_prob.mean()) if len(trailing) else float("nan"),fixtures_2026=int((part.year==2026).sum()),logloss_2026=float(part[part.year==2026].loss.mean())))
pd.DataFrame(segments).to_csv("research_results/ht_next_calibration_segments.csv",index=False)
print(summary.to_string(index=False),flush=True)
print(pd.DataFrame(segments).to_string(index=False),flush=True)
