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

# Diagnose whether stronger team ratings or a home-advantage change improves out-of-sample prices.
# Selection is based only on Bet365 last-seen market odds; market odds NEVER enter model fitting.
# Fetch only odds for the held-out league fixtures; avoid full JSON scans.
import time
odds={}
for period_start,period_end in (("2025-01-01","2026-01-01"),("2026-01-01","2026-11-13")):
 ids=[r["match_id"] for r in rows if period_start<=r["match_date"][:10]<period_end and r.get("match_id")]
 for offset in range(0,len(ids),15):
  batch=[]
  for attempt in range(4):
   try:
    batch=db.table("historical_match_odds").select("match_id,odds_payload").in_("match_id",ids[offset:offset+15]).execute().data or []
    break
   except Exception as exc:
    if "timeout" not in str(exc).lower() or attempt==3:raise
    time.sleep(2**attempt)
  for item in batch:
   for book in ((item.get("odds_payload") or {}).get("data") or {}).get("bookmakers",[]):
    if str(book.get("bookmaker","")).lower()!="bet365":continue
    m=(book.get("markets") or {}).get("match_odds") or {}
    try:
     q=[float(m[k]["last_seen"]) for k in ("home","draw","away")]
     if min(q)>1 and max(q)<1000:odds[item["match_id"]]=q
    except (KeyError,ValueError,TypeError):pass
    break
print("ODDS_AVAILABLE",len(odds),flush=True)

# Select parameters using 2025 only. Evaluate selected settings once on 2026.
# Multiplying attack/defence contrasts tests whether elite-vs-weak separation is too muted.
def evaluate(beta,test):
 ll=br=0.; fav_n=fav_hits=fav_prob=fav_market=0
 for match in test:
  p=probs(beta,match["home_team"],match["away_team"],"poisson")
  actual=0 if match["home_goals"]>match["away_goals"] else 1 if match["home_goals"]==match["away_goals"] else 2
  ll-=math.log(max(float(p[actual]),1e-12))
  br+=sum((float(p[k])-int(k==actual))**2 for k in range(3))
  q=odds.get(match.get("match_id"))
  if q:
   side=0 if q[0]<q[2] else 2
   if q[side]<1.5:
    fav_n+=1;fav_hits+=int(side==actual);fav_prob+=float(p[side])
    implied=[1/x for x in q];fav_market+=implied[side]/sum(implied)
 count=len(test)
 return dict(n=count,logloss=ll/count,brier=br/count,fav_n=fav_n,
             fav_actual=fav_hits/max(1,fav_n),fav_model=fav_prob/max(1,fav_n),
             fav_market=fav_market/max(1,fav_n))

train_2025=[r for r in rows if r["match_date"][:10]<"2025-01-01"]
test_2025=[r for r in rows if "2025-01-01"<=r["match_date"][:10]<"2026-01-01"]
train_2026=[r for r in rows if r["match_date"][:10]<"2026-01-01"]
test_2026=[r for r in rows if "2026-01-01"<=r["match_date"][:10]<"2026-11-13"]
if min(map(len,(train_2025,test_2025,train_2026,test_2026)))<30:
 raise RuntimeError("Insufficient chronological training/validation samples")
results=[]
for scale in (.125,.25,.5,1.):
 base=fit_strength(train_2025,date(2025,1,1),scale)
 for contrast in (1.0,1.15,1.3):
  for home_shift in (-.05,0.,.05):
   b=base.copy();b[2:]*=contrast;b[1]+=home_shift
   metrics=evaluate(b,test_2025)
   results.append((metrics["logloss"],scale,contrast,home_shift,metrics))
   print(f"SELECTION_2025 league={LEAGUE_ID} scale={scale} contrast={contrast} home_shift={home_shift} {metrics}",flush=True)
winner=min(results,key=lambda x:x[0])
_,scale,contrast,home_shift,selection_metrics=winner
print(f"SELECTED_2025 league={LEAGUE_ID} scale={scale} contrast={contrast} home_shift={home_shift} selection={selection_metrics}",flush=True)
b=fit_strength(train_2026,date(2026,1,1),scale)
b[2:]*=contrast;b[1]+=home_shift
selected=evaluate(b,test_2026)
baseline=fit_strength(train_2026,date(2026,1,1),.5)
reference=evaluate(baseline,test_2026)
print(f"FINAL_2026 league={LEAGUE_ID} selected={selected} baseline={reference}",flush=True)
