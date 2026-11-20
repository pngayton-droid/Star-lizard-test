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

# Three progressively richer strictly past-only probability forecasts.
# A: empirical frequency of second-half outcome for exact HT score, smoothed
#    towards prior overall outcome with 50-match pseudo-count.
# B: score plus prematch strength, xG, shots, corners, reds via logistic regression.
# C: B without xG to isolate incremental xG value.
from sklearn.metrics import log_loss
f["score_key"]=f.home_ht_goals.astype(int).astype(str)+"-"+f.away_ht_goals.astype(int).astype(str)
f["out_next"]=np.where(f.first_2h=="h",0,np.where(f.first_2h=="a",1,2))
f["out_over15"]=((f.goals_h+f.goals_a)>=2).astype(int)
f["out_2h_homewin"]=(f.goals_h>f.goals_a).astype(int)
f["out_2h_awaywin"]=(f.goals_a>f.goals_h).astype(int)
extra=["h_shots","a_shots","h_sot","a_sot","h_corners","a_corners","h_red","a_red"]
base=core+["ht_diff","ht_total","score_strength"]+extra
model_cols={"score_plus_stats":base,"score_plus_stats_xg":base+["home_ht_xg","away_ht_xg"]}
targets={"next_goal":("out_next",3),"over_1_5":("out_over15",2),"home_wins_2h":("out_2h_homewin",2),"away_wins_2h":("out_2h_awaywin",2)}
period=f.date.dt.to_period("M")
preds=[]
for month in sorted(period.unique()):
    tr=np.flatnonzero(period<month);te=np.flatnonzero(period==month)
    if len(tr)<1000 or len(te)<20:continue
    past=f.iloc[tr];future=f.iloc[te]
    for target,(ycol,nclass) in targets.items():
        prior=np.bincount(past[ycol].to_numpy(int),minlength=nclass)/len(past)
        by_score=past.groupby("score_key")[ycol].value_counts().unstack(fill_value=0)
        for k in te:
            r=f.iloc[k];counts=np.array([by_score.loc[r.score_key].get(i,0) for i in range(nclass)],float) if r.score_key in by_score.index else np.zeros(nclass)
            probs=(counts+50*prior)/(counts.sum()+50)
            for cls in range(nclass):
                preds.append((r.match_id,str(r.date.date()),int(r.date.year),r.score_key,target,cls,int(r[ycol]==cls),"exact_score_history",float(probs[cls]),int(counts.sum())))
        for name,cols in model_cols.items():
            scale=StandardScaler().fit(f.loc[tr,cols])
            X=scale.transform(f.loc[tr,cols]);Z=scale.transform(f.loc[te,cols])
            clf=LogisticRegression(C=1,max_iter=500).fit(X,past[ycol].to_numpy(int))
            prob=clf.predict_proba(Z)
            for j,k in enumerate(te):
                r=f.iloc[k]
                for cls in range(nclass):
                    val=float(prob[j,list(clf.classes_).index(cls)]) if cls in clf.classes_ else 0.
                    preds.append((r.match_id,str(r.date.date()),int(r.date.year),r.score_key,target,cls,int(r[ycol]==cls),name,val,-1))
p=pd.DataFrame(preds,columns=["match_id","date","year","ht_score","target","class","actual","model","prob","historical_same_score_n"])
p["prob"]=p.prob.clip(1e-9,1-1e-9)
p["brier"]=(p.prob-p.actual)**2
p["logloss"]=-(p.actual*np.log(p.prob)+(1-p.actual)*np.log1p(-p.prob))
# Multiclass outcomes are assessed with summed Brier and multiclass log loss.
group=p.groupby(["match_id","date","year","ht_score","target","model"],as_index=False).agg(brier=("brier","sum"),logloss=("logloss","sum"),historical_same_score_n=("historical_same_score_n","max"))
summary=group.groupby(["target","model"],as_index=False).agg(fixtures=("match_id","size"),mean_brier=("brier","mean"),mean_logloss=("logloss","mean"))
summary.to_csv("research_results/ht_score_similarity_summary.csv",index=False)
wide=group.pivot(index=["match_id","date","year","ht_score","target"],columns="model",values=["brier","logloss"]).dropna()
comparisons=[]
for target in targets:
    sub=wide.loc[wide.index.get_level_values("target")==target]
    for metric in ("brier","logloss"):
        for competitor in ("exact_score_history","score_plus_stats"):
            gain=sub[(metric,competitor)]-sub[(metric,"score_plus_stats_xg")]
            comparisons.append(dict(target=target,metric=metric,comparison=competitor+"_minus_full",fixtures=len(gain),gain=float(gain.mean()),positive_years=int(sum(gain[gain.index.get_level_values("year")==yr].mean()>0 for yr in sorted(gain.index.get_level_values("year").unique()))))
pd.DataFrame(comparisons).to_csv("research_results/ht_score_similarity_comparisons.csv",index=False)
# Exact score frequencies and outcome distributions, with strict minimum counts.
detail=[]
for score,subset in f.groupby("score_key"):
    if len(subset)<30:continue
    eval_ids=set(group[(group.ht_score==score)&(group.model=="score_plus_stats_xg")].match_id)
    tested=subset[subset.match_id.isin(eval_ids)]
    if len(tested)<20:continue
    detail.append(dict(ht_score=score,historical_matches=len(subset),evaluated_matches=len(tested),second_half_goals_mean=float((tested.goals_h+tested.goals_a).mean()),over_1_5_rate=float(tested.out_over15.mean()),next_home_rate=float((tested.out_next==0).mean()),next_away_rate=float((tested.out_next==1).mean()),no_next_goal_rate=float((tested.out_next==2).mean()),mean_ht_xg=float((tested.home_ht_xg+tested.away_ht_xg).mean()),mean_ht_corners=float((tested.h_corners+tested.a_corners).mean())))
pd.DataFrame(detail).sort_values("evaluated_matches",ascending=False).to_csv("research_results/ht_score_similarity_scorelines.csv",index=False)
print(summary.to_string(index=False),flush=True)
print(pd.DataFrame(comparisons).to_string(index=False),flush=True)
