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




from sklearn.linear_model import PoissonRegressor,HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from scipy.special import softmax
# Team and competition priors use only games completed on an earlier DATE.
# Date-only source cannot establish same-day kickoff order.
f["out_next"]=np.where(f.first_2h=="h",0,np.where(f.first_2h=="a",1,2))
f["league"]=f.competition_id.astype(str)
f["home_id"]=f.home_team.astype(str)
f["away_id"]=f.away_team.astype(str)
f["total_2h"]=f.goals_h+f.goals_a
base=["home_ht_goals","away_ht_goals","p_home","p_draw","p_away","ht_diff","ht_total","score_strength","h_shots","a_shots","h_sot","a_sot","h_corners","a_corners","h_red","a_red","home_ht_xg","away_ht_xg"]
priorcols=["home_for_prior","home_against_prior","away_for_prior","away_against_prior","league_2h_prior"]
# Every prior is calculated from strictly earlier dates, shrink to global means.
league_hist={}
team_hist={}
priorrows=[]
for date,day in f.groupby("date",sort=True):
    for r in day.itertuples():
        l=league_hist.get(r.league,(0.,0))
        def get(team):
            v=team_hist.get(team,(0.,0.,0.))
            return ((v[0]+15*0.8)/(v[2]+15),(v[1]+15*0.8)/(v[2]+15))
        hf,ha=get(r.home_id);af,aa=get(r.away_id)
        priorrows.append((r.Index,hf,ha,af,aa,(l[0]+30*1.55)/(l[1]+30)))
    for r in day.itertuples():
        old=league_hist.get(r.league,(0.,0))
        league_hist[r.league]=(old[0]+r.total_2h,old[1]+1)
        for team,gf,ga in ((r.home_id,r.goals_h,r.goals_a),(r.away_id,r.goals_a,r.goals_h)):
            a,b,n=team_hist.get(team,(0.,0.,0.))
            team_hist[team]=(a+gf,b+ga,n+1)
for i,col in enumerate(priorcols,1):
    f[col]=pd.Series({r[0]:r[i] for r in priorrows})
period=f.date.dt.to_period("M")
# Final three months frozen, never used for model selection or refitting.
months=sorted(period.unique())
holdout_start=months[-3]
records=[]
for month in months:
    te=np.flatnonzero(period==month)
    tr=np.flatnonzero(period<month)
    if len(tr)<1500 or len(te)<20:continue
    # Fixed hyperparameters; all variants trained on identical historical data.
    for name,cols in (("A0_logistic",base),("A1_tempo",base+priorcols)):
        scale=StandardScaler().fit(f.loc[tr,cols])
        clf=LogisticRegression(C=1,max_iter=400).fit(scale.transform(f.loc[tr,cols]),f.loc[tr,"out_next"])
        probs=clf.predict_proba(scale.transform(f.loc[te,cols]))
        for j,k in enumerate(te):
            records.append((k,str(month),name,float(-np.log(max(probs[j,int(f.loc[k,"out_next"])],1e-10)))))
    cols=base+priorcols
    scale=StandardScaler().fit(f.loc[tr,cols])
    xtr=scale.transform(f.loc[tr,cols]);xte=scale.transform(f.loc[te,cols])
    ph=PoissonRegressor(alpha=10,max_iter=250).fit(xtr,f.loc[tr,"goals_h"])
    pa=PoissonRegressor(alpha=10,max_iter=250).fit(xtr,f.loc[tr,"goals_a"])
    lh=np.maximum(ph.predict(xte),1e-8);la=np.maximum(pa.predict(xte),1e-8)
    none=np.exp(-lh-la)
    probs=np.stack([(1-none)*lh/(lh+la),(1-none)*la/(lh+la),none],axis=1)
    for j,k in enumerate(te):
        records.append((k,str(month),"A2_poisson",float(-np.log(max(probs[j,int(f.loc[k,"out_next"])],1e-10)))))
    # A3 is a non-monotone shallow ceiling check; do not claim monotonicity.
    clf=HistGradientBoostingClassifier(max_iter=100,max_leaf_nodes=7,l2_regularization=10,learning_rate=.04,random_state=42).fit(f.loc[tr,cols],f.loc[tr,"out_next"])
    probs=clf.predict_proba(f.loc[te,cols])
    for j,k in enumerate(te):
        records.append((k,str(month),"A3_shallow_boost",float(-np.log(max(probs[j,int(f.loc[k,"out_next"])],1e-10)))))
p=pd.DataFrame(records,columns=["idx","month","model","loss"])
p["year"]=f.loc[p.idx,"date"].dt.year.to_numpy()
p["state"]=np.where(f.loc[p.idx,"ht_diff"].to_numpy()>0,"home_leads",np.where(f.loc[p.idx,"ht_diff"].to_numpy()<0,"away_leads","draw"))
p["split"]=np.where(pd.PeriodIndex(p.month,freq="M")>=holdout_start,"holdout","development")
p.to_csv("research_results/ht_tempo_priors_predictions.csv",index=False)
summ=p.groupby(["split","model"],as_index=False).agg(fixtures=("loss","size"),logloss=("loss","mean"))
summ.to_csv("research_results/ht_tempo_priors_summary.csv",index=False)
wide=p.pivot(index="idx",columns="model",values="loss")
meta=p.drop_duplicates("idx").set_index("idx")
rows=[]
for split in ("development","holdout"):
    ids=meta.index[meta.split==split]
    for arm in ("A1_tempo","A2_poisson","A3_shallow_boost"):
        diff=(wide.loc[ids,"A0_logistic"]-wide.loc[ids,arm]).dropna()
        rows.append(dict(split=split,arm=arm,n=len(diff),gain=float(diff.mean()),positive_years=int(((wide.loc[ids,"A0_logistic"]-wide.loc[ids,arm]).groupby(meta.loc[ids,"year"]).mean()>0).sum())))
pd.DataFrame(rows).to_csv("research_results/ht_tempo_priors_comparisons.csv",index=False)
print(summ.to_string(index=False),flush=True)
print(pd.DataFrame(rows).to_string(index=False),flush=True)
