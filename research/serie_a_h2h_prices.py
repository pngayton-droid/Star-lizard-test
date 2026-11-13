"""STARLIZARD v2: opponent-adjusted goal/xG blend with held-out validation and Serie A prices."""
import os,math
from datetime import date
import numpy as np
from supabase import create_client
db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
rows=[]
for start in range(0,4000,500):
 b=db.table("historical_xg").select("match_date,home_team,away_team,home_xg,away_xg,home_goals,away_goals").eq("competition_id","comp_5840").lt("match_date","2026-11-21").order("match_date").range(start,start+499).execute().data or []
 rows+=b
 if len(b)<500:break
rows=[r for r in rows if all(r.get(k) is not None for k in ("match_date","home_xg","away_xg","home_goals","away_goals"))]
rows.sort(key=lambda r:r["match_date"])
teams=sorted(set(r["home_team"] for r in rows)|set(r["away_team"] for r in rows));idx={t:i for i,t in enumerate(teams)};n=len(teams)
fixtures=[("Como","Cagliari"),("Lazio","Lecce"),("Parma","Roma"),("Napoli","Torino"),("Juventus","Venezia"),("Bologna","Udinese"),("Sassuolo","Genoa"),("Milan","Frosinone"),("Atalanta","Inter"),("Monza","Fiorentina")]
print("TEAMS",teams,flush=True)
def fit(history,cutoff,blend):
 X=[];Y=[];W=[]
 for r in history:
  age=max(0,(cutoff-date.fromisoformat(r["match_date"][:10])).days);w=2**(-age/240)
  h,a=idx[r["home_team"]],idx[r["away_team"]]
  for attack,defence,home,xg,goals in [(h,a,1,r["home_xg"],r["home_goals"]),(a,h,0,r["away_xg"],r["away_goals"])]:
   v=np.zeros(2+2*n);v[0]=1;v[1]=home;v[2+attack]=1;v[2+n+defence]=-1
   X.append(v);Y.append(math.log((1-blend)*float(xg)+blend*float(goals)+.15));W.append(w)
 X=np.asarray(X);Y=np.asarray(Y);sw=np.sqrt(np.asarray(W));p=np.eye(X.shape[1])*8;p[0,0]=.001;p[1,1]=16
 return np.linalg.solve((X*sw[:,None]).T@(X*sw[:,None])+p,(X*sw[:,None]).T@(Y*sw))
def predict(beta,h,a):
 hi,ai=idx[h],idx[a]
 x=max(.15,math.exp(beta[0]+beta[1]+beta[2+hi]-beta[2+n+ai])-.15)
 y=max(.15,math.exp(beta[0]+beta[2+ai]-beta[2+n+hi])-.15)
 ph=[math.exp(-x)];pa=[math.exp(-y)]
 for k in range(1,13):ph.append(ph[-1]*x/k);pa.append(pa[-1]*y/k)
 p=[0.,0.,0.];rho=-.08
 for i in range(13):
  for j in range(13):
   tau=1.
   if i==j==0:tau=1-x*y*rho
   elif i==0 and j==1:tau=1+x*rho
   elif i==1 and j==0:tau=1+y*rho
   elif i==j==1:tau=1-rho
   p[0 if i>j else 1 if i==j else 2]+=max(0,tau)*ph[i]*pa[j]
 total=sum(p)
 return x,y,[v/total for v in p]
# Holdout: 2026 calendar year. Compare identical match subset for all blend candidates.
cutoff=date(2026,1,1)
train=[r for r in rows if r["match_date"][:10]<'2026-01-01']
test=[r for r in rows if r["match_date"][:10]>='2026-01-01']
print("TRAIN",len(train),"HOLDOUT",len(test),flush=True)
scores={}
for blend in (0.,.25,.5,.75,1.):
 beta=fit(train,cutoff,blend)
 loss=0.;brier=0.
 for r in test:
  p=predict(beta,r["home_team"],r["away_team"])[2]
  o=0 if r["home_goals"]>r["away_goals"] else 1 if r["home_goals"]==r["away_goals"] else 2
  loss-=math.log(max(1e-12,p[o]));brier+=sum((v-(k==o))**2 for k,v in enumerate(p))
 scores[blend]=loss/len(test)
 print(f"HOLDOUT blend={blend:.2f} logloss={loss/len(test):.5f} brier={brier/len(test):.5f}",flush=True)
best=min(scores,key=scores.get)
print("SELECTED_BLEND",best,flush=True)
beta=fit(rows,date(2026,11,20),best)
# Venue-only H2H, up to five meetings and up to five years old; limited data starts 2022.
def venue_h2h(p,h,a,cutoff):
 prior=[r for r in rows if r["home_team"]==h and r["away_team"]==a and r["match_date"][:10]<cutoff and (date.fromisoformat(cutoff)-date.fromisoformat(r["match_date"][:10])).days<=1826][-5:]
 if not prior:return p,0
 residual=sum(max(-2,min(2,int(r["home_goals"])-int(r["away_goals"]))) for r in prior)/len(prior)
 shift=.5*residual*len(prior)/(len(prior)+4)
 q=np.array(p)*np.exp(np.array([shift,0,-shift]));q=q/q.sum()
 return q.tolist(),len(prior)
for h,a in fixtures:
 if h not in idx or a not in idx:
  print("MISSING_TEAM",h,a,flush=True);continue
 x,y,p=predict(beta,h,a)
 q,count=venue_h2h(p,h,a,"2026-11-20")
 print(f"FIXTURE {h} v {a} H2H_N={count} BASE={1/p[0]:.3f},{1/p[1]:.3f},{1/p[2]:.3f} H2H_FAIR={1/q[0]:.3f},{1/q[1]:.3f},{1/q[2]:.3f}",flush=True)
