"""Chronological blind backtest: elite Spanish clubs priced 1.20–1.50 by Bet365."""
import os, math
from datetime import date
import numpy as np
from supabase import create_client

db=create_client(os.environ["SUPABASE_URL"],os.environ["SUPABASE_SECRET_KEY"])
def load(table,cols):
 out=[]
 for start in range(0,20000,500):
  q=db.table(table).select(cols).order("match_id").range(start,start+499)
  if table=="historical_xg":q=q.eq("competition_id","comp_8814")
  batch=q.execute().data or [];out.extend(batch)
  if len(batch)<500:break
 return out
matches=load("historical_xg","match_id,match_date,home_team,away_team,home_goals,away_goals,home_xg,away_xg")
matches=[m for m in matches if all(m.get(k) is not None for k in ("match_date","home_xg","away_xg","home_goals","away_goals"))]
matches.sort(key=lambda m:(m["match_date"],m["match_id"]))
odds={}
for r in load("historical_match_odds","match_id,odds_payload,fetch_status"):
 if r.get("fetch_status")!="collected":continue
 payload=r.get("odds_payload") or {}
 for b in (payload.get("data") or {}).get("bookmakers",[]):
  if b.get("bookmaker")=="Bet365":
   odds[r["match_id"]]=(b.get("markets") or {}).get("match_odds") or {};break
teams=sorted(set(m["home_team"] for m in matches)|set(m["away_team"] for m in matches))
idx={t:i for i,t in enumerate(teams)};n=len(teams);elite={"Real Madrid","Barcelona","Atlético Madrid"}
def fit(history,cutoff):
 X=[];Y=[];W=[]
 for m in history:
  age=max(0,(cutoff-date.fromisoformat(m["match_date"][:10])).days);w=2**(-age/180)
  h,a=idx[m["home_team"]],idx[m["away_team"]]
  for attack,defence,home,xg in [(h,a,1,m["home_xg"]),(a,h,0,m["away_xg"])]:
   row=np.zeros(2+2*n);row[0]=1;row[1]=home;row[2+attack]=1;row[2+n+defence]=-1
   X.append(row);Y.append(math.log(max(0,float(xg))+.15));W.append(w)
 X=np.asarray(X);Y=np.asarray(Y);sw=np.sqrt(np.asarray(W))
 penalty=np.eye(X.shape[1])*10;penalty[0,0]=.001;penalty[1,1]=20
 return np.linalg.solve((X*sw[:,None]).T@(X*sw[:,None])+penalty,(X*sw[:,None]).T@(Y*sw))
def probabilities(beta,home,away):
 h,a=idx[home],idx[away]
 x=max(.15,math.exp(beta[0]+beta[1]+beta[2+h]-beta[2+n+a])-.15)
 y=max(.15,math.exp(beta[0]+beta[2+a]-beta[2+n+h])-.15)
 p=[0.,0.,0.];rho=-.08
 ph=[math.exp(-x)];pa=[math.exp(-y)]
 for k in range(1,13):ph.append(ph[-1]*x/k);pa.append(pa[-1]*y/k)
 for i in range(13):
  for j in range(13):
   tau=1.
   if i==j==0:tau=1-x*y*rho
   elif i==0 and j==1:tau=1+x*rho
   elif i==1 and j==0:tau=1+y*rho
   elif i==j==1:tau=1-rho
   p[0 if i>j else 1 if i==j else 2]+=max(0,tau)*ph[i]*pa[j]
 return [z/sum(p) for z in p]
results=[];history=[];i=0;fitted=0
while i<len(matches):
 day=matches[i]["match_date"][:10];today=[]
 while i<len(matches) and matches[i]["match_date"][:10]==day:
  today.append(matches[i]);i+=1
 eligible=[]
 for m in today:
  o=odds.get(m["match_id"],{})
  for club,side in ((m["home_team"],"home"),(m["away_team"],"away")):
   if club not in elite:continue
   try:price=float(o[side]["last_seen"])
   except (KeyError,ValueError,TypeError):continue
   if 1.2<=price<=1.5:eligible.append((m,club,side,price))
 if eligible and len(history)>=100:
  beta=fit(history,date.fromisoformat(day));fitted+=1
  for m,club,side,price in eligible:
   p=probabilities(beta,m["home_team"],m["away_team"])[0 if side=="home" else 2]
   won=(m["home_goals"]>m["away_goals"]) if side=="home" else (m["away_goals"]>m["home_goals"])
   results.append((club,price,p,int(won),day))
 history.extend(today)
print("MATCHES",len(matches),"ODDS_MATCHES",len(odds),"ELIGIBLE_EVALUATED",len(results),"FITTED_DAYS",fitted,flush=True)
for club in ["Real Madrid","Barcelona","Atlético Madrid","ALL"]:
 rows=[r for r in results if r[0]==club or club=="ALL"]
 if not rows:continue
 n=len(rows);wins=sum(r[3] for r in rows);model=sum(r[2] for r in rows)/n;book=sum(1/r[1] for r in rows)/n
 roi=sum((r[1]-1 if r[3] else -1) for r in rows)/n
 logloss=sum(-(r[3]*math.log(max(1e-10,r[2]))+(1-r[3])*math.log(max(1e-10,1-r[2]))) for r in rows)/n
 print(f"{club}: n={n} wins={wins} actual={wins/n:.4f} model={model:.4f} book_raw={book:.4f} roi={roi:.4f} model_logloss={logloss:.4f}",flush=True)
