"""Decompose strong-favourite errors without fitting to bookmaker prices.
Select favourite groups from independent Bet365 closing odds only for diagnostic reporting.
"""
import os,math,time
from datetime import date
import numpy as np
from supabase import create_client
import pathlib
source=pathlib.Path(__file__).with_name("published_models_holdout.py").read_text()
exec(compile(source.split("from scipy.stats import skellam")[0], "published_models_holdout.py", "exec"), globals())

test=[r for r in rows if "2026-01-01"<=r["match_date"][:10]<"2026-11-13"]
train=[r for r in rows if r["match_date"][:10]<"2026-01-01"]
beta=fit_strength(train,date(2026,1,1),.5)
odds={}
ids=[r["match_id"] for r in test if r.get("match_id")]
for off in range(0,len(ids),15):
 for attempt in range(4):
  try:
   batch=db.table("historical_match_odds").select("match_id,odds_payload").in_("match_id",ids[off:off+15]).execute().data or []
   break
  except Exception:
   if attempt==3:raise
   time.sleep(2**attempt)
 for item in batch:
  for book in ((item.get("odds_payload") or {}).get("data") or {}).get("bookmakers",[]):
   if str(book.get("bookmaker","")).lower()!="bet365":continue
   m=(book.get("markets") or {}).get("match_odds") or {}
   try:
    q=[float(m[k]["last_seen"]) for k in ("home","draw","away")]
    if min(q)>1:odds[item["match_id"]]=q
   except (KeyError,TypeError,ValueError):pass
   break
def calc(lh,la,rho):
 ph=poisson.pmf(np.arange(14),lh);pa=poisson.pmf(np.arange(14),la)
 p=np.zeros(3)
 for i in range(14):
  for j in range(14):
   tau=1.
   if i==j==0:tau=1-lh*la*rho
   elif i==0 and j==1:tau=1+lh*rho
   elif i==1 and j==0:tau=1+la*rho
   elif i==j==1:tau=1-rho
   p[0 if i>j else 1 if i==j else 2]+=max(0,tau)*ph[i]*pa[j]
 return p/p.sum()
groups={}
for r in test:
 q=odds.get(r.get("match_id"))
 if not q:continue
 side=0 if q[0]<q[2] else 2
 if q[side]>=1.5:continue
 h,a=idx[r["home_team"]],idx[r["away_team"]]
 lh=math.exp(np.clip(beta[0]+beta[1]+beta[2+h]-beta[2+n+a],-7,5))
 la=math.exp(np.clip(beta[0]+beta[2+a]-beta[2+n+h],-7,5))
 y=0 if r["home_goals"]>r["away_goals"] else 1 if r["home_goals"]==r["away_goals"] else 2
 key="HOME" if side==0 else "AWAY"
 g=groups.setdefault(key,[])
 g.append((side,y,lh,la,q))
for key,g in groups.items():
 print("GROUP",LEAGUE_ID,key,"n",len(g),flush=True)
 for rho in (-.12,-.08,0.,.08):
  for contrast in (1.,1.15,1.3):
   pred=draw=actual=market=0.
   for side,y,lh,la,q in g:
    if side==0:x,z=lh*contrast,la/contrast
    else:x,z=lh/contrast,la*contrast
    p=calc(x,z,rho)
    pred+=p[side];draw+=p[1];actual+=int(y==side)
    v=np.array([1/k for k in q]);market+=v[side]/sum(v)
   print("DIAGNOSTIC",LEAGUE_ID,key,"rho",rho,"contrast",contrast,"n",len(g),"actual",round(actual/len(g),4),"pred",round(pred/len(g),4),"draw",round(draw/len(g),4),"market_devig",round(market/len(g),4),flush=True)
