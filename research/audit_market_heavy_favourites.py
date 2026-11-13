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

# Frozen model. Odds select matches only; model fit and probabilities never use odds.
odds={}
for start in range(0,20000,500):
 batch=db.table("historical_match_odds").select("match_id,odds_payload").eq("fetch_status","collected").range(start,start+499).execute().data or []
 for item in batch:
  data=(item.get("odds_payload") or {}).get("data") or {}
  for book in data.get("bookmakers") or []:
   if str(book.get("bookmaker","")).lower()=="bet365":
    m=(book.get("markets") or {}).get("match_odds") or {}
    for phase in ("opening","last_seen"):
     try:
      vals=[float(m[k][phase]) for k in ("home","draw","away")]
      if min(vals)>1 and max(vals)<1000:
       odds.setdefault(item["match_id"],{})[phase]=vals
     except (KeyError,TypeError,ValueError):pass
    break
 if len(batch)<500:break
print("ODDS_MATCHES",len(odds),"OPENING",sum("opening" in x for x in odds.values()),"LAST_SEEN",sum("last_seen" in x for x in odds.values()),flush=True)
for cutoff,end in (("2025-01-01","2026-01-01"),("2026-01-01","2026-11-13")):
 train=[r for r in rows if r["match_date"][:10]<cutoff]
 test=[r for r in rows if cutoff<=r["match_date"][:10]<end]
 beta=fit_strength(train,date.fromisoformat(cutoff),.5)
 for phase in ("opening","last_seen"):
  groups={k:[] for k in ("under_1.30","1.30_to_1.49","1.50_to_1.79","1.80_plus")}
  for r in test:
   q=odds.get(r.get("match_id"),{}).get(phase)
   if not q:continue
   side=0 if q[0]<q[2] else 2
   price=q[side]
   if price>=1.5: key="1.50_to_1.79" if price<1.8 else "1.80_plus"
   elif price<1.3:key="under_1.30"
   else:key="1.30_to_1.49"
   if key=="1.80_plus":continue
   market=[1/v for v in q]; total=sum(market);market=[v/total for v in market]
   p=probs(beta,r["home_team"],r["away_team"],"poisson")
   actual=int((r["home_goals"]>r["away_goals"] if side==0 else r["away_goals"]>r["home_goals"]))
   groups[key].append((float(p[side]),float(market[side]),actual,price))
  for key,items in groups.items():
   if not items:continue
   a=np.array(items)
   print(f"FAV_AUDIT league={LEAGUE_ID} period={cutoff} phase={phase} band={key} n={len(a)} model_pred={a[:,0].mean():.4f} market_devig={a[:,1].mean():.4f} actual={a[:,2].mean():.4f} model_gap={a[:,2].mean()-a[:,0].mean():+.4f} market_gap={a[:,2].mean()-a[:,1].mean():+.4f}",flush=True)
