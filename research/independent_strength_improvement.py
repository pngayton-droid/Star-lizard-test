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


# Independent experiment: tune xG-vs-goals blend, team shrinkage, decay, and contrast.
# 2025 validation chooses hyperparameters; 2026 remains untouched.
def fit_variant(hist,cutoff,shrink,blend,halflife):
 X,Y,G,W=matrix(hist,cutoff)
 X=X.astype(float)
 # Y from matrix is 50/50; reconstruct xG using Y and goals.
 target=2*Y-G
 target=blend*target+(1-blend)*G
 # Override original 240-day weights with chosen half life
 W=[]
 for m in hist:
  age=max(0,(cutoff-date.fromisoformat(m["match_date"][:10])).days)
  w=2**(-age/halflife)
  W.extend([w,w])
 W=np.asarray(W)
 pen=np.ones(X.shape[1])*shrink
 pen[0]=.001;pen[1]=shrink*2
 def fun(b):
  eta=np.clip(X@b,-7,5);mu=np.exp(eta)
  return np.sum(W*(mu-target*eta))+.5*np.sum(pen*b*b),X.T@(W*(mu-target))+pen*b
 b=np.zeros(X.shape[1]);b[0]=np.log(max(.2,np.average(target,weights=W)))
 res=minimize(fun,b,jac=True,method="L-BFGS-B",options={"maxiter":200})
 if not res.success:print("OPT_WARNING",res.message,flush=True)
 return res.x
def metrics(beta, matches):
 ll=br=0.
 bins={k:[0,0.,0.] for k in ("strong","medium","other")}
 for m in matches:
  p=probs(beta,m["home_team"],m["away_team"],"poisson")
  y=0 if m["home_goals"]>m["away_goals"] else 1 if m["home_goals"]==m["away_goals"] else 2
  ll-=math.log(max(float(p[y]),1e-12))
  br+=sum((float(p[k])-int(k==y))**2 for k in range(3))
  side=0 if p[0]>p[2] else 2
  strength=float(p[side])
  key="strong" if strength>=.65 else "medium" if strength>=.5 else "other"
  bins[key][0]+=1;bins[key][1]+=strength;bins[key][2]+=int(side==y)
 return {"n":len(matches),"logloss":ll/len(matches),"brier":br/len(matches),
  "bins":{k:{"n":v[0],"pred":round(v[1]/v[0],4) if v[0] else None,"actual":round(v[2]/v[0],4) if v[0] else None} for k,v in bins.items()}}
train25=[r for r in rows if r["match_date"][:10]<"2025-01-01"]
val25=[r for r in rows if "2025-01-01"<=r["match_date"][:10]<"2026-01-01"]
train26=[r for r in rows if r["match_date"][:10]<"2026-01-01"]
test26=[r for r in rows if "2026-01-01"<=r["match_date"][:10]<"2026-11-13"]
if min(map(len,(train25,val25,train26,test26)))<30:raise RuntimeError("Not enough samples")
results=[]
for shrink in (1.,4.,8.,16.):
 for blend in (.25,.5,.75):
  for halflife in (120,240,480):
   b=fit_variant(train25,date(2025,1,1),shrink,blend,halflife)
   m=metrics(b,val25)
   results.append((m["logloss"],shrink,blend,halflife))
best=min(results)
print("SELECTION_2025",LEAGUE_ID,best,flush=True)
for label,params in (("BASELINE",(8.,.5,240)),("TUNED",best[1:])):
 b=fit_variant(train26,date(2026,1,1),*params)
 print("FINAL_2026",LEAGUE_ID,label,params,metrics(b,test26),flush=True)
