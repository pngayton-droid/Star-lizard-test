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


from sklearn.neighbors import NearestNeighbors
from sklearn.linear_model import LogisticRegression
f["score_key"]=f.home_ht_goals.astype(int).astype(str)+"-"+f.away_ht_goals.astype(int).astype(str)
f["out_next"]=np.where(f.first_2h=="h",0,np.where(f.first_2h=="a",1,2))
f["out_over15"]=((f.goals_h+f.goals_a)>=2).astype(int)
f["out_2h_homewin"]=(f.goals_h>f.goals_a).astype(int)
f["out_2h_awaywin"]=(f.goals_a>f.goals_h).astype(int)
targets={"next_goal":("out_next",3),"over_1_5":("out_over15",2),"home_wins_2h":("out_2h_homewin",2),"away_wins_2h":("out_2h_awaywin",2)}
cols=["p_home","p_draw","p_away","h_shots","a_shots","h_sot","a_sot","h_corners","a_corners","h_red","a_red","home_ht_xg","away_ht_xg"]
# Exact score matching first, then nearest in halftime conditions.
# Each feature standardized using ONLY past training data.
# Fixed k=50 and k=100; not tuned on evaluated outcomes.
period=f.date.dt.to_period("M")
rows=[]
for month in sorted(period.unique()):
    tr=np.flatnonzero(period<month);te=np.flatnonzero(period==month)
    if len(tr)<1000 or len(te)<20:continue
    past=f.iloc[tr];future=f.iloc[te]
    scale=StandardScaler().fit(past[cols])
    X=scale.transform(past[cols]);Z=scale.transform(future[cols])
    # Logistic comparison is identical in inputs and C to prior score+stats+xG model.
    logcols=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away","ht_diff","ht_total","score_strength","h_shots","a_shots","h_sot","a_sot","h_corners","a_corners","h_red","a_red","home_ht_xg","away_ht_xg"]
    ls=StandardScaler().fit(past[logcols])
    LX=ls.transform(past[logcols]);LZ=ls.transform(future[logcols])
    for target,(ycol,nclass) in targets.items():
        y=past[ycol].to_numpy(int)
        prior=np.bincount(y,minlength=nclass)/len(y)
        clf=LogisticRegression(C=1,max_iter=500).fit(LX,y)
        lp=clf.predict_proba(LZ)
        for j,k in enumerate(te):
            r=f.iloc[k]
            actual=int(r[ycol])
            same=np.flatnonzero(past.score_key.to_numpy()==r.score_key)
            counts=np.bincount(y[same],minlength=nclass)
            baseline=(counts+50*prior)/(len(same)+50)
            all_models={"exact_score_history":baseline,"logistic_stats_xg":lp[j]}
            if len(same)>=20:
                # Score must match exactly; closest statistical profiles among same-score matches.
                delta=X[same]-Z[j]
                dist=np.einsum("ij,ij->i",delta,delta)
                nearest=same[np.argsort(dist,kind="stable")]
                for n in (50,100):
                    take=nearest[:min(n,len(nearest))]
                    ct=np.bincount(y[take],minlength=nclass)
                    # Shrink toward same-score historical distribution for sparse neighbours.
                    all_models["neighbours_"+str(n)]=(ct+10*baseline)/(len(take)+10)
            for name,probs in all_models.items():
                probs=np.maximum(np.asarray(probs,float),1e-9)
                probs=probs/probs.sum()
                loss=float(-np.log(probs[actual]))
                brier=float(np.sum((probs-np.eye(nclass)[actual])**2))
                rows.append((r.match_id,str(r.date.date()),int(r.date.year),r.score_key,target,name,len(same),actual,loss,brier,float(probs[actual])))
p=pd.DataFrame(rows,columns=["match_id","date","year","ht_score","target","model","prior_same_score_n","actual","logloss","brier","prob_actual"])
if p.empty:raise RuntimeError("No evaluated fixtures")
summary=p.groupby(["target","model"],as_index=False).agg(fixtures=("match_id","size"),logloss=("logloss","mean"),brier=("brier","mean"),mean_prior_same_score=("prior_same_score_n","mean"))
summary.to_csv("research_results/ht_neighbours_summary.csv",index=False)
paired=p.pivot(index=["match_id","date","year","ht_score","target"],columns="model",values=["logloss","brier"])
comparisons=[]
for target in targets:
    sub=paired.loc[paired.index.get_level_values("target")==target]
    for model in ("exact_score_history","neighbours_50","neighbours_100"):
        for metric in ("logloss","brier"):
            v=sub[[(metric,model),(metric,"logistic_stats_xg")]].dropna()
            if v.empty:continue
            gain=v[(metric,"logistic_stats_xg")]-v[(metric,model)]
            yrs=gain.index.get_level_values("year")
            comparisons.append(dict(target=target,model=model,metric=metric,fixtures=len(gain),gain_vs_logistic=float(gain.mean()),positive_years=int(sum(gain[yrs==yr].mean()>0 for yr in sorted(yrs.unique()))),years=len(yrs),gain_2026=float(gain[yrs==2026].mean())))
pd.DataFrame(comparisons).to_csv("research_results/ht_neighbours_comparisons.csv",index=False)
by_score=p[p.model.isin(["neighbours_50","logistic_stats_xg"])].groupby(["ht_score","target","model"],as_index=False).agg(fixtures=("match_id","size"),logloss=("logloss","mean"))
by_score=by_score[by_score.fixtures>=30]
by_score.to_csv("research_results/ht_neighbours_scorelines.csv",index=False)
print(summary.to_string(index=False),flush=True)
print(pd.DataFrame(comparisons).to_string(index=False),flush=True)
