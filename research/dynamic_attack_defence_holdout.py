"""Experimental chronological score-driven attack/defence ratings; not a published-model replication."""
import os, math
from datetime import date
import numpy as np
from scipy.optimize import minimize_scalar
from supabase import create_client

LEAGUE=os.environ.get("LEAGUE_ID","comp_5840")
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
rows=[]
for start in range(0,4000,250):
    page=db.table("historical_xg").select("match_date,home_team,away_team,home_xg,away_xg,home_goals,away_goals").eq("competition_id",LEAGUE).lt("match_date","2026-11-13").order("match_date").range(start,start+249).execute().data or []
    rows.extend(page)
    if len(page)<250:break
rows=[r for r in rows if all(r.get(k) is not None for k in ("match_date","home_xg","away_xg","home_goals","away_goals"))]
rows.sort(key=lambda r:(r["match_date"],r["home_team"],r["away_team"]))
teams=sorted(set(r["home_team"] for r in rows)|set(r["away_team"] for r in rows))
idx={t:i for i,t in enumerate(teams)}
N=len(teams)
def probabilities(lh,la):
    ph=[math.exp(-lh)];pa=[math.exp(-la)]
    for k in range(1,13):
        ph.append(ph[-1]*lh/k);pa.append(pa[-1]*la/k)
    p=np.zeros(3)
    for i,x in enumerate(ph):
        for j,y in enumerate(pa):p[0 if i>j else 1 if i==j else 2]+=x*y
    return p/p.sum()
def simulate(params):
    lr,blend,decay,home=params
    attack=np.zeros(N);defence=np.zeros(N)
    # Each side's attack and defence are separate, updated after every match.
    out=[]
    previous=None
    for r in rows:
        dt=date.fromisoformat(r["match_date"][:10])
        if previous is not None:
            gap=(dt-previous).days
            if gap>0:
                factor=math.exp(-gap/decay)
                attack*=factor;defence*=factor
        previous=dt
        h=idx[r["home_team"]];a=idx[r["away_team"]]
        lh=math.exp(np.clip(math.log(1.35)+home+attack[h]-defence[a],-3,2.5))
        la=math.exp(np.clip(math.log(1.35)+attack[a]-defence[h],-3,2.5))
        p=probabilities(lh,la)
        y=0 if r["home_goals"]>r["away_goals"] else 1 if r["home_goals"]==r["away_goals"] else 2
        out.append((dt,p,y,lh,la))
        # Simultaneous updates: do not let the first side's update affect the second.
        gh=blend*float(r["home_xg"])+(1-blend)*float(r["home_goals"])
        ga=blend*float(r["away_xg"])+(1-blend)*float(r["away_goals"])
        eh=np.clip((gh-lh)/(1+lh),-1.5,1.5)
        ea=np.clip((ga-la)/(1+la),-1.5,1.5)
        attack[h]+=lr*eh;defence[a]-=lr*eh
        attack[a]+=lr*ea;defence[h]-=lr*ea
        attack-=attack.mean();defence-=defence.mean()
    return out
def evaluate(out,year,temp=1.):
    selected=[(p,y) for d,p,y,_,_ in out if d.year==year]
    if not selected:raise RuntimeError("No year samples")
    loss=brier=0.
    fav=[0,0.,0.]
    for p,y in selected:
        q=np.maximum(p,1e-9)**(1/temp);q=q/q.sum()
        loss-=math.log(max(q[y],1e-12))
        brier+=sum((q[k]-(k==y))**2 for k in range(3))
        side=0 if q[0]>=q[2] else 2
        if q[side]>=.65:
            fav[0]+=1;fav[1]+=float(q[side]);fav[2]+=int(side==y)
    return {"n":len(selected),"logloss":loss/len(selected),"brier":brier/len(selected),"strong_n":fav[0],"strong_pred":fav[1]/fav[0] if fav[0] else None,"strong_actual":fav[2]/fav[0] if fav[0] else None}
assert sum(d.year==2025 for d,_,_,_,_ in simulate((.04,.5,365,0.15)))>40
candidates=[]
for lr in (.02,.06,.12):
 for blend in (0.,.5,.75):
  for decay in (240.,720.):
   for home in (.1,.25):
    params=(lr,blend,decay,home)
    out=simulate(params)
    m=evaluate(out,2025)
    candidates.append((m["logloss"],params))
best=min(candidates)
baseline=(.06,.5,365.,.15)
for label,params in (("BASELINE_DYNAMIC",baseline),("SELECTED_DYNAMIC",best[1])):
 out=simulate(params)
 print("RESULT",LEAGUE,label,"params",params,"validation_2025",evaluate(out,2025),"holdout_2026",evaluate(out,2026),flush=True)
 if label=="SELECTED_DYNAMIC":
    # Temperature calibrated only on 2025 predictions, then frozen for 2026.
    optimum=minimize_scalar(lambda t:evaluate(out,2025,t)["logloss"],bounds=(.7,1.6),method="bounded")
    print("RESULT",LEAGUE,"SELECTED_DYNAMIC_CALIBRATED","temperature",round(optimum.x,4),"holdout_2026",evaluate(out,2026,optimum.x),flush=True)
print("BEST_2025",LEAGUE,best,flush=True)
