"""Compare legacy log-xG ridge with correctly fitted Poisson goal model and venue H2H."""
import os, math
from datetime import date
import numpy as np
from scipy.optimize import minimize
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
LEAGUE_ID=os.environ.get("LEAGUE_ID","comp_3039")
rows=[]
for start in range(0,4000,500):
 b=db.table("historical_xg").select("match_id,match_date,home_team,away_team,home_xg,away_xg,home_goals,away_goals").eq("competition_id",LEAGUE_ID).lt("match_date","2026-11-13").order("match_date").range(start,start+499).execute().data or []
 rows+=b
 if len(b)<500:break
rows=[r for r in rows if all(r.get(k) is not None for k in ("match_date","home_xg","away_xg","home_goals","away_goals"))]
rows.sort(key=lambda r:r["match_date"])
teams=sorted(set(r["home_team"] for r in rows)|set(r["away_team"] for r in rows));idx={t:i for i,t in enumerate(teams)};n=len(teams)
def matrix(hist,cutoff):
 X=[];Y=[];G=[];W=[]
 for r in hist:
  age=max(0,(cutoff-date.fromisoformat(r["match_date"][:10])).days)
  w=2**(-age/240)
  h,a=idx[r["home_team"]],idx[r["away_team"]]
  for attack,defence,home,xg,goals in ((h,a,1,r["home_xg"],r["home_goals"]),(a,h,0,r["away_xg"],r["away_goals"])):
   v=np.zeros(2+2*n);v[0]=1;v[1]=home;v[2+attack]=1;v[2+n+defence]=-1
   X.append(v);Y.append(.5*float(xg)+.5*float(goals));G.append(float(goals));W.append(w)
 return np.array(X),np.array(Y),np.array(G),np.array(W)
def fit(hist,cutoff,kind):
 X,Y,G,W=matrix(hist,cutoff)
 pen=np.ones(X.shape[1])*8;pen[0]=.001;pen[1]=16
 if kind=="legacy":
  z=np.log(Y+.15);sw=np.sqrt(W)
  return np.linalg.solve((X*sw[:,None]).T@(X*sw[:,None])+np.diag(pen),(X*sw[:,None]).T@(z*sw))
 def fun(b):
  eta=np.clip(X@b,-7,5);mu=np.exp(eta)
  loss=np.sum(W*(mu-Y*eta))+.5*np.sum(pen*b*b)
  grad=X.T@(W*(mu-Y))+pen*b
  return loss,grad
 initial=np.zeros(X.shape[1]);initial[0]=np.log(max(.2,np.average(Y,weights=W)))
 res=minimize(fun,initial,jac=True,method="L-BFGS-B",options={"maxiter":250})
 if not res.success:print("OPT_WARNING",res.message,flush=True)
 return res.x
def probs(beta,h,a,kind):
 hi,ai=idx[h],idx[a]
 x=beta[0]+beta[1]+beta[2+hi]-beta[2+n+ai]
 y=beta[0]+beta[2+ai]-beta[2+n+hi]
 x=max(.15,np.exp(np.clip(x,-7,5))-(.15 if kind=="legacy" else 0))
 y=max(.15,np.exp(np.clip(y,-7,5))-(.15 if kind=="legacy" else 0))
 ph=[math.exp(-x)];pa=[math.exp(-y)]
 for k in range(1,14):ph.append(ph[-1]*x/k);pa.append(pa[-1]*y/k)
 p=np.zeros(3);rho=-.08
 for i in range(14):
  for j in range(14):
   tau=1.
   if i==j==0:tau=1-x*y*rho
   elif i==0 and j==1:tau=1+x*rho
   elif i==1 and j==0:tau=1+y*rho
   elif i==j==1:tau=1-rho
   p[0 if i>j else 1 if i==j else 2]+=max(0,tau)*ph[i]*pa[j]
 return p/p.sum()
def h2h(p,r,history,strength=.2):
 prior=[z for z in history if z["home_team"]==r["home_team"] and z["away_team"]==r["away_team"] and z["match_date"]<r["match_date"] and (date.fromisoformat(r["match_date"][:10])-date.fromisoformat(z["match_date"][:10])).days<=1826][-5:]
 if not prior:return p
 gd=sum(max(-2,min(2,int(z["home_goals"])-int(z["away_goals"]))) for z in prior)/len(prior)
 shift=strength*gd*len(prior)/(len(prior)+4)
 q=p*np.exp([shift,0,-shift])
 return q/q.sum()
def fit_strength(hist,cutoff,scale):
 X,Y,G,W=matrix(hist,cutoff)
 pen=np.ones(X.shape[1])*8*scale;pen[0]=.001;pen[1]=16*scale
 def fun(b):
  eta=np.clip(X@b,-7,5);mu=np.exp(eta)
  return np.sum(W*(mu-Y*eta))+.5*np.sum(pen*b*b), X.T@(W*(mu-Y))+pen*b
 b=np.zeros(X.shape[1]);b[0]=np.log(max(.2,np.average(Y,weights=W)))
 return minimize(fun,b,jac=True,method="L-BFGS-B",options={"maxiter":250}).x


from scipy.stats import skellam
from sklearn.isotonic import IsotonicRegression
from collections import defaultdict

def dc_fit(history, cutoff):
 # Dixon-Coles: goal-count Poisson likelihood, low-score correction and exponential decay.
 X,Y,G,W=matrix(history,cutoff)
 # Separate rows are home and away goal observations.
 pairs=[(float(r["home_goals"]),float(r["away_goals"])) for r in history]
 def objective(v):
  beta=v[:-1];rho=float(v[-1])
  eta=np.clip(X@beta,-6,5);mu=np.exp(eta)
  base=np.sum(W*(mu-G*eta))
  hmu=mu[::2];amu=mu[1::2];weights=W[::2]
  low=0.
  for k,(hg,ag) in enumerate(pairs):
   if hg>1 or ag>1:continue
   x,y=hmu[k],amu[k]
   tau=1-x*y*rho if hg==0 and ag==0 else 1+x*rho if hg==0 else 1+y*rho if ag==0 else 1-rho
   if tau<=0:return 1e10
   low-=weights[k]*math.log(tau)
  penalty=np.sum(beta[2:]**2)*0.5+beta[1]**2*0.5
  return base+low+penalty
 b=np.zeros(X.shape[1]+1);b[0]=np.log(max(.2,np.average(G,weights=W)));b[-1]=-.05
 res=minimize(objective,b,method="L-BFGS-B",bounds=[(None,None)]*len(X[0])+[(-.15,.15)],options={"maxiter":90})
 if not res.success:print("DC_OPT_WARNING",res.message,flush=True)
 return res.x

def dc_predict(params,match):
 beta=params[:-1];rho=params[-1]
 h,a=idx[match["home_team"]],idx[match["away_team"]]
 x=np.exp(np.clip(beta[0]+beta[1]+beta[2+h]-beta[2+n+a],-6,5))
 y=np.exp(np.clip(beta[0]+beta[2+a]-beta[2+n+h],-6,5))
 ph=[math.exp(-x)];pa=[math.exp(-y)]
 for k in range(1,14):ph.append(ph[-1]*x/k);pa.append(pa[-1]*y/k)
 p=np.zeros(3)
 for i in range(14):
  for j in range(14):
   tau=1-x*y*rho if i==j==0 else 1+x*rho if i==0 and j==1 else 1+y*rho if i==1 and j==0 else 1-rho if i==j==1 else 1.
   p[0 if i>j else 1 if i==j else 2]+=max(0,tau)*ph[i]*pa[j]
 return p/p.sum()

def wilkens_raw(match,history,window=3):
 # Only previous matches, and same home/away context. No market input.
 prior_home=[r for r in history if r["home_team"]==match["home_team"] and r["match_date"]<match["match_date"]][-window:]
 prior_away=[r for r in history if r["away_team"]==match["away_team"] and r["match_date"]<match["match_date"]][-window:]
 if len(prior_home)<window or len(prior_away)<window:return None
 x=np.mean([float(r["home_xg"]) for r in prior_home]);y=np.mean([float(r["away_xg"]) for r in prior_away])
 x=max(.05,x);y=max(.05,y)
 p=np.array([skellam.sf(0,x,y),skellam.pmf(0,x,y),skellam.cdf(-1,x,y)])
 return p/p.sum()

def result(m,p):
 outcome=0 if m["home_goals"]>m["away_goals"] else 1 if m["home_goals"]==m["away_goals"] else 2
 return outcome,float(-math.log(max(1e-12,p[outcome]))),float(sum((p[k]-int(k==outcome))**2 for k in range(3)))


import json
from pathlib import Path
FIXTURES=[
 ("2026-11-21","Como","Cagliari"),("2026-11-21","Lazio","Lecce"),
 ("2026-11-21","Parma","Roma"),("2026-11-21","Napoli","Torino"),
 ("2026-11-22","Juventus","Venezia"),("2026-11-22","Bologna","Udinese"),
 ("2026-11-22","Sassuolo","Genoa"),("2026-11-22","Milan","Frosinone"),
 ("2026-11-22","Atalanta","Inter"),("2026-11-23","Monza","Fiorentina")]
assert LEAGUE_ID=="comp_5840"
cutoff="2026-11-13"
history=[r for r in rows if r["match_date"][:10]<cutoff]
cal=[r for r in history if "2025-01-01"<=r["match_date"][:10]<"2026-01-01"]
before_cal=[r for r in history if r["match_date"][:10]<"2025-01-01"]
cal_preds=[]
for m in cal:
 prior=before_cal+[z for z in cal if z["match_date"]<m["match_date"]]
 p=wilkens_raw(m,prior)
 if p is not None:cal_preds.append((p,result(m,p)[0]))
if len(cal_preds)<50:raise RuntimeError("Insufficient historical calibration")
iso=[]
for k in range(3):
 model=IsotonicRegression(y_min=.01,y_max=.99,out_of_bounds="clip")
 model.fit([p[k] for p,y in cal_preds],[int(y==k) for p,y in cal_preds])
 iso.append(model)
base=fit_strength(history,date.fromisoformat(cutoff),.5)
dc=dc_fit(history,date.fromisoformat(cutoff))
outputs=[]
for dt,h,a in FIXTURES:
 m={"match_date":dt,"home_team":h,"away_team":a}
 if h not in idx or a not in idx:raise RuntimeError(f"Unknown team: {h} {a}")
 raw=wilkens_raw(m,history)
 models={"STARLIZARD":probs(base,h,a,"poisson"),"DIXON_COLES":dc_predict(dc,m)}
 if raw is not None:
  calibrated=np.array([float(iso[k].predict([raw[k]])[0]) for k in range(3)])
  models["WILKENS_STYLE"]=calibrated/calibrated.sum()
 else:
  models["WILKENS_STYLE"]=None
 record={"date":dt,"home":h,"away":a,"models":{}}
 for name,p in models.items():
  record["models"][name]=None if p is None else {"probabilities":[round(float(v),6) for v in p],"fair_odds":[round(1/float(v),3) for v in p]}
 outputs.append(record)
 print("FIXTURE_PREDICTION",json.dumps({"date":dt,"home":h,"away":a,"model":name,"result":record["models"][name]}),flush=True)
Path("prediction_output").mkdir(exist_ok=True)
Path("prediction_output/serie_a_2026_11_21_23.json").write_text(json.dumps({"data_cutoff":cutoff,"bookmaker_odds_used":False,"predictions":outputs},indent=2))
