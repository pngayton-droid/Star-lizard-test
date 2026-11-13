"""Compare legacy log-xG ridge with correctly fitted Poisson goal model and venue H2H."""
import os, math
from datetime import date
import numpy as np
from scipy.optimize import minimize
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
rows=[]
for start in range(0,4000,500):
 b=db.table("historical_xg").select("match_date,home_team,away_team,home_xg,away_xg,home_goals,away_goals").eq("competition_id","comp_5840").lt("match_date","2026-11-13").order("match_date").range(start,start+499).execute().data or []
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
# Two separate forward validation periods, fixed parameters, training strictly before each.
for cutoff,end in (("2025-01-01","2026-01-01"),("2026-01-01","2026-11-13")):
 train=[r for r in rows if r["match_date"][:10]<cutoff]
 test=[r for r in rows if cutoff<=r["match_date"][:10]<end]
 print("PERIOD",cutoff,"TRAIN",len(train),"TEST",len(test),flush=True)
 if not train or not test:continue
 for kind in ("legacy","poisson"):
  beta=fit(train,date.fromisoformat(cutoff),kind)
  for with_h2h in (False,True):
   ll=br=0.;f_n=f_win=f_pred=0
   for r in test:
    p=probs(beta,r["home_team"],r["away_team"],kind)
    if with_h2h:p=h2h(p,r,train)
    outcome=0 if r["home_goals"]>r["away_goals"] else 1 if r["home_goals"]==r["away_goals"] else 2
    ll-=math.log(max(1e-12,p[outcome]));br+=sum((p[k]-(k==outcome))**2 for k in range(3))
    if max(p[0],p[2])>=.6:
     f_n+=1;f_win+=int(outcome==(0 if p[0]>=p[2] else 2));f_pred+=max(p[0],p[2])
   print(f"RESULT period={cutoff} model={kind} venue_h2h={with_h2h} n={len(test)} logloss={ll/len(test):.6f} brier={br/len(test):.6f} strong_n={f_n} strong_actual={f_win/max(1,f_n):.4f} strong_pred={f_pred/max(1,f_n):.4f}",flush=True)

# Refit through the available history and publish fresh model odds for the provisional fixture list.
fixtures=[("Como","Cagliari"),("Lazio","Lecce"),("Parma","Roma"),("Napoli","Torino"),("Juventus","Venezia"),("Bologna","Udinese"),("Sassuolo","Genoa"),("Milan","Frosinone"),("Atalanta","Inter"),("Monza","Fiorentina")]
beta=fit(rows,date(2026,11,20),"poisson")
for home,away in fixtures:
 if home not in idx or away not in idx:
  print("PRICE_MISSING",home,away,flush=True);continue
 p=probs(beta,home,away,"poisson")
 r={"home_team":home,"away_team":away,"match_date":"2026-11-20"}
 q=h2h(p,r,rows)
 print(f"PRICE {home} v {away} base={1/p[0]:.3f},{1/p[1]:.3f},{1/p[2]:.3f} h2h={1/q[0]:.3f},{1/q[1]:.3f},{1/q[2]:.3f}",flush=True)
