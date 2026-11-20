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




from sklearn.linear_model import PoissonRegressor
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from scipy.special import softmax

# A0 inputs and training protocol match the winning next-goal benchmark.
# Other markets are NEW models: their quality must be assessed independently.
from sklearn.metrics import log_loss, brier_score_loss
f["date"]=pd.to_datetime(f.match_date)
f["second_half_result"]=np.select([f.goals_h>f.goals_a,f.goals_h<f.goals_a],["home","away"],default="draw")
f["next_goal"]=f.first_2h.map({"h":"home","a":"away","none":"none"})
f["total_2h"]=f.goals_h+f.goals_a
targets={
    "next_goal":f.next_goal,
    "second_half_result":f.second_half_result,
    "over_0_5_2h":(f.total_2h>=1).astype(int),
    "over_1_5_2h":(f.total_2h>=2).astype(int),
    "over_2_5_2h":(f.total_2h>=3).astype(int),
    "home_scores_2h":(f.goals_h>=1).astype(int),
    "away_scores_2h":(f.goals_a>=1).astype(int),
    "both_score_2h":((f.goals_h>=1)&(f.goals_a>=1)).astype(int),
}
cols=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away",
      "ht_diff","ht_total","score_strength","h_shots","a_shots",
      "h_sot","a_sot","h_corners","a_corners","h_red","a_red",
      "home_ht_xg","away_ht_xg"]
f=f.sort_values(["date","match_id"]).reset_index(drop=True)
# Recreate targets after sorting so positional labels remain aligned.
targets={
    "next_goal":f.first_2h.map({"h":"home","a":"away","none":"none"}),
    "second_half_result":np.select([f.goals_h>f.goals_a,f.goals_h<f.goals_a],["home","away"],default="draw"),
    "over_0_5_2h":(f.total_2h>=1).astype(int),
    "over_1_5_2h":(f.total_2h>=2).astype(int),
    "over_2_5_2h":(f.total_2h>=3).astype(int),
    "home_scores_2h":(f.goals_h>=1).astype(int),
    "away_scores_2h":(f.goals_a>=1).astype(int),
    "both_score_2h":((f.goals_h>=1)&(f.goals_a>=1)).astype(int),
}
period=f.date.dt.to_period("M")
months=sorted(period.unique())
holdout_start=months[-3]
rows=[]
for month in months:
    test=np.flatnonzero(period==month)
    train=np.flatnonzero(period<month)
    if len(train)<1500 or len(test)<20:continue
    scaler=StandardScaler().fit(f.loc[train,cols])
    xtrain=scaler.transform(f.loc[train,cols])
    xtest=scaler.transform(f.loc[test,cols])
    for market,y in targets.items():
        y=np.asarray(y)
        model=LogisticRegression(C=1,max_iter=400)
        model.fit(xtrain,y[train])
        probabilities=model.predict_proba(xtest)
        classes=model.classes_
        for j,idx in enumerate(test):
            for k,selection in enumerate(classes):
                prob=float(probabilities[j,k])
                rows.append({
                    "match_id":f.loc[idx,"match_id"],
                    "match_date":f.loc[idx,"match_date"],
                    "home_team":f.loc[idx,"home_team"],
                    "away_team":f.loc[idx,"away_team"],
                    "ht_score":str(int(f.loc[idx,"home_ht_goals"]))+"-"+str(int(f.loc[idx,"away_ht_goals"])),
                    "month":str(month),
                    "split":"holdout" if month>=holdout_start else "development",
                    "market":market,"selection":str(selection),
                    "probability":prob,"fair_odds":1/prob if prob>0 else np.inf,
                    "won":int(y[idx]==selection),
                })
pred=pd.DataFrame(rows)
if pred.empty:raise RuntimeError("No walk-forward predictions generated")
pred.to_csv("research_results/ht_second_half_fair_odds_predictions.csv",index=False)
summary=[]
for (split,market),g in pred.groupby(["split","market"]):
    # One row per match in each class; evaluate proper multiclass log loss.
    wide=g.pivot(index="match_id",columns="selection",values="probability")
    outcomes=g.loc[g.won==1].set_index("match_id")["selection"].reindex(wide.index)
    if outcomes.isna().any():raise RuntimeError("Missing outcome for "+market)
    ptrue=np.array([wide.loc[mid,selection] for mid,selection in outcomes.items()])
    summary.append({
        "split":split,"market":market,"fixtures":len(wide),
        "logloss":float(-np.log(np.clip(ptrue,1e-12,1)).mean()),
        "classes":len(wide.columns),
    })
pd.DataFrame(summary).to_csv("research_results/ht_second_half_fair_odds_summary.csv",index=False)
print(pd.DataFrame(summary).to_string(index=False),flush=True)
print("Historical walk-forward prices only; no bookmaker ROI or live fixture predictions.",flush=True)
